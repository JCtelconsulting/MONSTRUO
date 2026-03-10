import sys
import os
import json
from pathlib import Path

# Agregar el directorio actual al path para importar el core
# En el contenedor, esto es /app/code
sys.path.append(str(Path(__file__).resolve().parent))

from app.core import db

TABLE_MAPPING = {
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

def migrate():
    print("Iniciando migración a esquemas...")
    conn = db.get_conn()
    try:
        # 1. Crear esquemas
        for schema in TABLE_MAPPING.keys():
            print(f"Creando esquema '{schema}'...")
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")
        
        # 2. Mover tablas
        for schema, tables in TABLE_MAPPING.items():
            for table in tables:
                # Verificar si la tabla existe en public antes de moverla
                sql_check = "SELECT 1 FROM pg_catalog.pg_tables WHERE schemaname = 'public' AND tablename = %s"
                check = conn._conn.execute(sql_check, (table,)).fetchone()
                
                if check:
                    print(f"Moviendo '{table}' -> '{schema}.{table}'...")
                    conn.execute(f"ALTER TABLE public.{table} SET SCHEMA {schema};")
                else:
                    print(f"Omitiendo '{table}' (ya movida o no existe en public)")
        
        conn.commit()
        print("Migración completada con éxito.")
    except Exception as e:
        conn.rollback()
        print(f"ERROR durante la migración: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
