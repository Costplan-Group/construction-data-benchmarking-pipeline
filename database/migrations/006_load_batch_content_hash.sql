/*
Add content-hash idempotency for workbook uploads.

Repeat uploads of the same file bytes link to the existing LoadBatch
instead of creating a duplicate ingestion run.
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF COL_LENGTH('stg.LoadBatch', 'ContentHash') IS NULL
   AND OBJECT_ID('stg.LoadBatch', 'U') IS NOT NULL
BEGIN
    ALTER TABLE stg.LoadBatch ADD ContentHash CHAR(64) NULL;
END;
GO

IF OBJECT_ID('stg.LoadBatch', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1
       FROM sys.indexes
       WHERE name = 'UX_LoadBatch_ContentHash'
         AND object_id = OBJECT_ID('stg.LoadBatch')
   )
BEGIN
    CREATE UNIQUE INDEX UX_LoadBatch_ContentHash
        ON stg.LoadBatch (ContentHash)
        WHERE ContentHash IS NOT NULL;
END;
GO
