import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from app.core import db

SCHEMAS = {
    "auth": ["users", "sessions"],
    "tks": [
        "tickets", "ticket_comments", "ticket_attachments", "user_specialties", 
        "ticket_transitions", "ticket_emails", "ticket_notifications", 
        "ticket_automation_rules", "ticket_config_client_emails", "ticket_approvals", 
        "ticket_legal_holds", "ticket_email_drafts", "ticket_email_draft_attachments", 
        "ticket_notification_attempts"
    ],
    "erp": [
        "laudus_customers", "laudus_invoices", "laudus_payments", "customers", 
        "invoices", "invoice_items", "parrotfy_invoices", "parrotfy_payments", 
        "bank_accounts", "bank_statements", "bank_statement_lines", "bank_reconciliations", 
        "billing_rules", "invoice_templates", "invoice_template_items", "billing_profiles", 
        "billing_profile_recipients", "invoice_dispatches", "invoice_events", "uf_rates", 
        "collection_actions"
    ],
    "crm": ["crm_interactions", "customer_contacts"],
    "bodega": [
        "products", "inventory_movements", "parrotfy_inventory", "parrotfy_stock_snapshot", 
        "laudus_stock_snapshot", "conciliacion_bodega_runs", "conciliacion_bodega_diffs", 
        "stock_snapshots"
    ],
    "core": ["alerts", "sys_jobs", "system_settings", "audit_logs", "evidence_events", "migration_log", "test_migration_table"],
    "ia": ["ia_eventos", "ia_bodega_casos", "ai_event_queue", "ai_recommendations"],
    "ops": [
        "bridge_messages", "jira_import_runs", "compliance_export_runs", 
        "compliance_purge_runs", "jira_issue_map", "jira_sync_runs", 
        "jira_sync_cursor", "parallel_kpi_daily", "parallel_decisions"
    ],
    "cat": ["cat_categorias", "cat_items", "cat_match_queue", "cat_fuente_map", "cat_item_categories"],
    "pmo": ["pmo_proyectos", "pmo_bitacora_ia"],
    "fundacion": ["fundacion_tareas"]
}

def clean_ghost_tables():
    conn = db.get_conn()
    try:
        # Build reverse map: table -> correct_schema
        table_to_correct_schema = {}
        for schema, tables in SCHEMAS.items():
            for t in tables:
                table_to_correct_schema[t] = schema

        all_schemas = list(SCHEMAS.keys()) + ["public"]
        
        dropped = 0
        for target_schema in all_schemas:
            # Query all tables in this schema
            rows = conn.execute(
                "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = %s",
                (target_schema,)
            ).fetchall()
            
            for row in rows:
                table_name = row["tablename"]
                correct_schema = table_to_correct_schema.get(table_name)
                
                # If we know where it belongs, and this is NOT the correct schema
                if correct_schema and target_schema != correct_schema:
                    # Double check if correct schema really has it
                    has_correct = conn.execute(
                        "SELECT 1 FROM pg_catalog.pg_tables WHERE schemaname = %s AND tablename = %s",
                        (correct_schema, table_name)
                    ).fetchone()
                    
                    if has_correct:
                        print(f"Limpiando tabla fantasma: {target_schema}.{table_name} (Datos en {correct_schema})")
                        conn.execute(f"DROP TABLE {target_schema}.{table_name} CASCADE;")
                        dropped += 1
                    else:
                        print(f"WARNING: {target_schema}.{table_name} está en el esquema equivocado pero no existe en {correct_schema}!")
        
        conn.commit()
        print(f"Limpieza exhaustiva finalizada. {dropped} tablas fantasmas eliminadas.")
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    clean_ghost_tables()
