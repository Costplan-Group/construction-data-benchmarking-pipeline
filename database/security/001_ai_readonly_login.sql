/*
  Create (or update) a dedicated read-only SQL login for the AI SQL assistant.

  Idempotent: safe to run more than once.
  Password is never stored in this file — pass it at run time.

  Grants SELECT on committed warehouse tables only: dbo.Dim* and dbo.Fact*
  (knowledge-base / AI SQL Assistant). Staging remains for report writing
  via the ingestion login, not this user.

  Example (sqlcmd / PowerShell one-liner):

    sqlcmd -S your_server -d your_database -E -i database/security/001_ai_readonly_login.sql -v LoginName=ai_readonly -v Password=REPLACE_ME

  Defaults if LoginName is omitted: ai_readonly. Password is required.
*/

SET NOCOUNT ON;
GO

DECLARE @LoginName sysname = N'$(LoginName)';
DECLARE @Password  nvarchar(128) = N'$(Password)';

-- sqlcmd leaves $(Var) unsubstituted when -v is missing
IF @LoginName = N'$(LoginName)' OR @LoginName LIKE N'$(%'
    SET @LoginName = N'ai_readonly';

IF @Password = N'$(Password)' OR @Password LIKE N'$(%' OR LTRIM(RTRIM(@Password)) = N''
BEGIN
    RAISERROR('Password sqlcmd variable is required. Pass -v Password=...', 16, 1);
    RETURN;
END;

DECLARE @sql nvarchar(max);
DECLARE @obj nvarchar(512);

-- Server login
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = @LoginName)
BEGIN
    SET @sql = N'CREATE LOGIN ' + QUOTENAME(@LoginName)
             + N' WITH PASSWORD = ' + QUOTENAME(@Password, '''')
             + N', CHECK_POLICY = ON';
    EXEC sys.sp_executesql @sql;
END;

-- Database user
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = @LoginName)
BEGIN
    SET @sql = N'CREATE USER ' + QUOTENAME(@LoginName)
             + N' FOR LOGIN ' + QUOTENAME(@LoginName);
    EXEC sys.sp_executesql @sql;
END;

-- SELECT on all dbo.Dim* / dbo.Fact* tables (re-applied each run)
DECLARE grant_cursor CURSOR LOCAL FAST_FORWARD FOR
    SELECT QUOTENAME(SCHEMA_NAME(t.schema_id)) + N'.' + QUOTENAME(t.name)
    FROM sys.tables AS t
    WHERE SCHEMA_NAME(t.schema_id) = N'dbo'
      AND (
            t.name LIKE N'Dim%'
         OR t.name LIKE N'Fact%'
         OR t.name LIKE N'fact%'
      );

OPEN grant_cursor;
FETCH NEXT FROM grant_cursor INTO @obj;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @sql = N'GRANT SELECT ON OBJECT::' + @obj + N' TO ' + QUOTENAME(@LoginName);
    EXEC sys.sp_executesql @sql;
    FETCH NEXT FROM grant_cursor INTO @obj;
END;
CLOSE grant_cursor;
DEALLOCATE grant_cursor;

PRINT N'AI read-only login ready: ' + @LoginName + N' (SELECT on dbo.Dim* / dbo.Fact*)';
GO
