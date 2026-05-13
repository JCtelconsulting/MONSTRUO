-- Registro de Message-IDs ya procesados por el poller IMAP.
-- Sirve para idempotencia: si el mismo correo entra dos veces (re-entrega,
-- reset de UIDVALIDITY, reprocesamiento manual, etc.), no se crea un ticket
-- duplicado y se marca Seen para sacarlo del flujo.
--
-- Diseño robusto: NO depende del flag IMAP \Seen como única defensa.
-- El poll usa cursor por UID + esta tabla para dedupe.
--
-- Idempotente: se puede correr varias veces.

CREATE TABLE IF NOT EXISTS tks.processed_email_messages (
    message_id   TEXT PRIMARY KEY,
    ticket_id    BIGINT NULL,
    uid          BIGINT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_processed_email_messages_ticket_id
    ON tks.processed_email_messages (ticket_id);
