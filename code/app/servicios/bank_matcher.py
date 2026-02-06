from datetime import datetime, timedelta
from app.core.db import get_conn

class BankMatcher:
    def __init__(self):
        pass

    def match_statement(self, statement_id: int):
        conn = get_conn()
        try:
            # 1. Get the Statement and its Lines (Source)
            stmt = conn.execute("SELECT * FROM bank_statements WHERE id=%s", (statement_id,)).fetchone()
            if not stmt:
                raise ValueError("Statement not found")

            # Determine Target Lines (Counterpart)
            # If this statement is Real (uploaded), target is Ledger (Synced).
            # If this statement is Ledger, target is Real.
            # Heuristic: Filename "SYNC_LAUDUS..." => Ledger. Else => Real.
            
            is_ledger = stmt["filename"].startswith("SYNC_LAUDUS")
            bank_account_id = stmt["bank_account_id"]
            
            # Target Criteria:
            # Same Bank Account.
            # Different Statement Source (if I am real, find ledger. if I am ledger, find real).
            # Not already reconciled.
            
            # Fetch Source Lines (Unreconciled)
            source_lines = conn.execute("""
                SELECT * FROM bank_statement_lines 
                WHERE statement_id=%s 
                AND reconciled_at IS NULL
            """, (statement_id,)).fetchall()
            
            results = {"exact": 0, "suggested": 0}
            
            for line in source_lines:
                # Find Candidates in Target Statements
                # We look for ALL statements of the OPPOSITE type for this bank account.
                # Simplified: matches against ANY line of the same bank_account that is NOT this statement.
                
                # Broad Query for candidates
                # Match logic:
                # Amount must correspond.
                # If Real Line is Output (-100), Ledger should have... Output (-100)?
                # Yes, because both represent "Movement in Bank".
                # Laudus Ledger: Credit (Salida) -> -100.
                # Real Bank: Cargo (Salida) -> -100.
                # So Amount must be equal.
                
                # Candidate Query
                candidates_q = """
                    SELECT l.*, s.filename 
                    FROM bank_statement_lines l
                    JOIN bank_statements s ON l.statement_id = s.id
                    WHERE s.bank_account_id = %s 
                    AND s.id != %s
                    AND l.reconciled_at IS NULL
                    AND l.amount = %s
                """
                candidates = conn.execute(candidates_q, (bank_account_id, statement_id, line["amount"])).fetchall()
                
                best_match = None
                match_type = None
                confidence = 0.0
                
                # Strategy 1: Exact Match (Doc Number + Amount)
                if line["document_number"]:
                    for cand in candidates:
                        if cand["document_number"] == line["document_number"]:
                            best_match = cand
                            match_type = "exact"
                            confidence = 1.0
                            break
                            
                # Strategy 2: Fuzzy Match (Date Range +/- 3 days)
                if not best_match and candidates:
                    line_date = datetime.strptime(line["date"], "%Y-%m-%d")
                    for cand in candidates:
                        cand_date = datetime.strptime(cand["date"], "%Y-%m-%d")
                        diff = abs((line_date - cand_date).days)
                        if diff <= 3:
                            # If multiple fuzzies, pick closest? For now, pick first.
                            best_match = cand
                            match_type = "fuzzy"
                            confidence = 0.8
                            break
                
                if best_match:
                    # Register Recommendation
                    # We store it in bank_reconciliations.
                    # match_id = best_match['id'] (The ID of the counterpart line)
                    
                    # Check if recommendation already exists?
                    existing = conn.execute("""
                        SELECT id FROM bank_reconciliations 
                        WHERE statement_line_id=%s AND match_type != 'manual'
                    """, (line["id"],)).fetchone()
                    
                    if not existing:
                        conn.execute("""
                            INSERT INTO bank_reconciliations 
                            (statement_line_id, match_type, match_id, confidence, created_at, created_by)
                            VALUES (%s, %s, %s, %s, NOW(), 'system')
                        """, (line["id"], match_type, str(best_match["id"]), confidence))
                        
                        if confidence == 1.0:
                            results["exact"] += 1
                        else:
                            results["suggested"] += 1
            
            conn.commit()
            return results
            
        finally:
            conn.close()
