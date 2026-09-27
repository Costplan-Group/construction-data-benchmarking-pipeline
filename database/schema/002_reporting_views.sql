/*
  Curated Power BI / reporting views over committed warehouse tables (dbo.Dim* / dbo.Fact*).

  Run after Dim/Fact tables exist (typically after at least one successful usp_CommitBatch,
  or after warehouse DDL has been applied).

  These views do NOT read staging (stg.*).

  DimCostSet has one row per (ProjectID, ContractorKey, CostStage); re-ingesting upserts that
  row in place, so every row is current and no IsCurrent/DataStatus filtering is needed.
*/

-- Drop legacy staging-era tender view if present
IF OBJECT_ID('dbo.vw_BI_TenderReview', 'V') IS NOT NULL
    DROP VIEW dbo.vw_BI_TenderReview;
GO

IF OBJECT_ID('dbo.vw_BI_ProjectOverview', 'V') IS NOT NULL
    DROP VIEW dbo.vw_BI_ProjectOverview;
GO

CREATE VIEW dbo.vw_BI_ProjectOverview
AS
SELECT
    p.ProjectKey,
    p.ProjectID,
    p.ProjectName,
    p.ClientName,
    p.LocationKey,
    loc.DisplayLabel AS LocationLabel,
    loc.Country,
    loc.Region,
    p.SectorKey,
    sec.SectorCode,
    sec.SectorName,
    cs.CostSetKey,
    cs.GIFA,
    cs.CostStage,
    cs.BaseDate,
    cs.Currency,
    c.ContractorKey,
    c.ContractorName AS SelectedContractorName,
    p.CreatedAt AS ProjectCreatedAt,
    p.UpdatedAt AS ProjectUpdatedAt
FROM dbo.DimProject AS p
LEFT JOIN dbo.DimSector AS sec
    ON sec.SectorKey = p.SectorKey
LEFT JOIN dbo.DimLocation AS loc
    ON loc.LocationKey = p.LocationKey
LEFT JOIN dbo.DimCostSet AS cs
    ON cs.ProjectKey = p.ProjectKey
LEFT JOIN dbo.DimContractor AS c
    ON c.ContractorKey = cs.ContractorKey;
GO

IF OBJECT_ID('dbo.vw_BI_Level2CostBreakdown', 'V') IS NOT NULL
    DROP VIEW dbo.vw_BI_Level2CostBreakdown;
GO

CREATE VIEW dbo.vw_BI_Level2CostBreakdown
AS
SELECT
    f.costSetKey AS CostSetKey,
    f.elementL2Key AS ElementL2Key,
    cs.ProjectKey,
    p.ProjectID,
    p.ProjectName,
    cs.CostStage,
    cs.GIFA,
    e.L1Code,
    e.L1Name,
    e.L2Code,
    e.L2Name,
    f.TotalCost,
    f.Comment,
    f.CreatedAt AS FactCreatedAt,
    CASE
        WHEN cs.GIFA IS NULL OR cs.GIFA = 0 THEN NULL
        ELSE f.TotalCost / cs.GIFA
    END AS CostPerM2
FROM dbo.FactElementCostL2 AS f
INNER JOIN dbo.DimCostSet AS cs
    ON cs.CostSetKey = f.costSetKey
INNER JOIN dbo.DimProject AS p
    ON p.ProjectKey = cs.ProjectKey
LEFT JOIN dbo.DimElementL2 AS e
    ON e.ElementL2Key = f.elementL2Key;
GO

IF OBJECT_ID('dbo.vw_BI_AdjustmentSummary', 'V') IS NOT NULL
    DROP VIEW dbo.vw_BI_AdjustmentSummary;
GO

CREATE VIEW dbo.vw_BI_AdjustmentSummary
AS
SELECT
    f.CostSetKey,
    f.adjustmentTypeKey AS AdjustmentTypeKey,
    cs.ProjectKey,
    p.ProjectID,
    p.ProjectName,
    cs.CostStage,
    adj.AdjCategory,
    adj.AdjSubType,
    f.Amount,
    f.Method,
    f.RatePercent,
    f.appliedToBase AS AppliedToBase,
    f.includedInComparison AS IncludedInComparison
FROM dbo.FactCostAdjustment AS f
INNER JOIN dbo.DimCostSet AS cs
    ON cs.CostSetKey = f.CostSetKey
INNER JOIN dbo.DimProject AS p
    ON p.ProjectKey = cs.ProjectKey
LEFT JOIN dbo.DimAdjustmentType AS adj
    ON adj.AdjustmentTypeKey = f.adjustmentTypeKey;
GO

IF OBJECT_ID('dbo.vw_BI_CostSetSummary', 'V') IS NOT NULL
    DROP VIEW dbo.vw_BI_CostSetSummary;
GO

CREATE VIEW dbo.vw_BI_CostSetSummary
AS
SELECT
    s.costSetKey AS CostSetKey,
    cs.ProjectKey,
    p.ProjectID,
    p.ProjectName,
    cs.GIFA,
    cs.CostStage,
    cs.Currency,
    c.ContractorKey,
    c.ContractorName,
    s.measuredWorksTotal AS MeasuredWorksTotal,
    s.buildingWorksEstimate AS BuildingWorksEstimate,
    s.totalInclRisk AS TotalInclRisk,
    s.totalInclInflation AS TotalInclInflation,
    s.grandTotal AS GrandTotal,
    CASE
        WHEN cs.GIFA IS NULL OR cs.GIFA = 0 THEN NULL
        ELSE s.grandTotal / cs.GIFA
    END AS GrandTotalPerM2
FROM dbo.FactCostSetSummary AS s
INNER JOIN dbo.DimCostSet AS cs
    ON cs.CostSetKey = s.costSetKey
INNER JOIN dbo.DimProject AS p
    ON p.ProjectKey = cs.ProjectKey
LEFT JOIN dbo.DimContractor AS c
    ON c.ContractorKey = cs.ContractorKey;
GO
