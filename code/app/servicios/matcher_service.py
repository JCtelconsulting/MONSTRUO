from datetime import datetime
from typing import Dict
from app.core import db


class MatcherService:
    def __init__(self):
        pass

    def match_statement_to_invoices(self, statement_id: int) -> Dict[str, int]:
        """
        Matches Bank Lines (from statement_id) against Open Invoices (ISSUED, not PAID).
        Criteria:
        1. Exact Amount Match within +/- 3 days.
        2. RUT Match in Description (future).
        """
        conn = db.get_conn()
        try:
            # 1. Get Source Lines (Bank Deposits > 0)
            # We only care about Money IN (Deposits) to match with Sales Invoices.
            # Withdrawals would match with Purchase Invoices (not yet in scope).

            lines = conn.execute(
                """
                SELECT * FROM bank_statement_lines 
                WHERE statement_id=%s 
                AND amount > 0 
                AND reconciled_at IS NULL
            """,
                (statement_id,),
            ).fetchall()

            results = {"exact": 0, "suggested": 0}

            # 2. Get Open Invoices Candidates
            # Filter by status ISSUED? Or DRAFT too? Ideally ISSUED.
            # And 'LAUDUS' or 'LOCAL' origin doesn't matter, we want to pay them.
            # We fetch ALL open invoices to memory or query per line?
            # Querying per line might be safer for date window.

            for line in lines:
                line_date = datetime.strptime(line["date"], "%Y-%m-%d")
                amount = line["amount"]

                # Window: +/- 5 days (Banks can be slow, or user pays late)
                # Query:
                # - Status NOT PAID
                # - Total Final approx Amount (allow small diff?)
                # - Date close

                # STRICT MATCH First: Exact Amount (tolerance 1.0)
                candidates_q = """
                    SELECT id, created_at, customer_id, total_final, external_id
                    FROM invoices 
                    WHERE status != 'PAID'
                    AND ABS(total_final - %s) < 5.0
                """
                candidates = conn.execute(candidates_q, (amount,)).fetchall()

                best_match = None
                confidence = 0.0

                for cand in candidates:
                    # Check Date
                    # Invoice Created At (Timestamp) vs Payment Date (Date)
                    # Payment should be >= Invoice Date (usually)
                    inv_date = datetime.fromisoformat(cand["created_at"]).date()
                    days_diff = (line_date.date() - inv_date).days

                    # Rule: Payment usually AFTER invoice. But allow small prepay (-5 to +90 days)
                    if -5 <= days_diff <= 90:
                        # Score Calculation
                        amount_diff = abs(cand["total_final"] - amount)

                        if amount_diff < 1.0:
                            conf = 0.95  # Exact Amount Match
                        elif amount_diff < 50.0:
                            conf = 0.80  # Very close amount
                        else:
                            continue  # Skip if amount is not close (query filtered by 50 already)

                        # Boost if Invoice ID is in description
                        # Extract numeric part of external_id (e.g. E00000715 -> 715)
                        inv_ref = str(cand.get("external_id") or cand.get("id"))
                        numeric_ref = "".join(filter(str.isdigit, inv_ref))

                        if (
                            numeric_ref
                            and len(numeric_ref) > 2
                            and numeric_ref in line["description"]
                        ):
                            conf = 1.0

                        # Lower confidence if date is very far
                        if days_diff > 60:
                            conf -= 0.1

                        if conf > confidence:
                            confidence = conf
                            best_match = cand

                if best_match:
                    # Register Recommendation
                    # We store it in bank_reconciliations.
                    # match_id = best_match['id'] (The ID of the counterpart line)

                    # Check existing
                    existing = conn.execute(
                        """
                        SELECT id FROM bank_reconciliations 
                        WHERE statement_line_id=%s
                    """,
                        (line["id"],),
                    ).fetchone()

                    if not existing:
                        conn.execute(
                            """
                            INSERT INTO bank_reconciliations 
                            (statement_line_id, match_type, match_id, confidence, created_at, created_by)
                            VALUES (%s, 'invoice', %s, %s, NOW(), 'system')
                        """,
                            (line["id"], str(best_match["id"]), confidence),
                        )

                        if confidence > 0.9:
                            results["exact"] += 1
                        else:
                            results["suggested"] += 1

            conn.commit()
            return results

        finally:
            conn.close()
