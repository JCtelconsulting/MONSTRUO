import sys
from pathlib import Path

# Agregar el directorio code/ al path
sys.path.append(str(Path(__file__).resolve().parent))

from app.core import db

# Lista de tablas que movimos a esquemas
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
    "core": ["alerts", "sys_jobs", "system_settings", "audit_logs", "evidence_events"],
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

def cleanup():
    print("Iniciando limpieza de tablas duplicadas en esquema public...")
    conn = db.get_conn()
    try:
        for schema, tables in SCHEMAS.items():
            for table in tables:
                # Verificar si existe en public
                check_public = conn.execute(
                    "SELECT 1 FROM pg_catalog.pg_tables WHERE schemaname = 'public' AND tablename = %s",
                    (table,)
                ).fetchone()
                
                # Verificar si existe en el esquema destino (donde están los datos)
                check_dest = conn.execute(
                    "SELECT 1 FROM pg_catalog.pg_tables WHERE schemaname = %s AND tablename = %s",
                    (schema, table)
                ).fetchone()
                
                if check_public and check_dest:
                    print(f"Eliminando tabla vacía: public.{table} (los datos están en {schema}.{table})")
                    conn.execute(f"DROP TABLE public.{table} CASCADE;")
                elif check_public:
                    print(f"Omitiendo public.{table} porque NO tiene duplicado en {schema}")
        
        conn.commit()
        print("Limpieza completada.")
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    cleanup()
