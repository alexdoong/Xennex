using System;
using System.Collections.Generic;

namespace Xennex.Models.LocalAi;

public sealed class AiSpecialist
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public int Revision { get; set; }
    public string Name { get; set; } = "";
    public string Role { get; set; } = "";
    public string Model { get; set; } = "";
    public string Instructions { get; set; } = "";
}
public sealed class AiMember
{
    public string SpecialistId { get; set; } = "";
    public bool SharePlan { get; set; } = true;
    public bool ShareHistory { get; set; } = true;
    public bool ShareNotebook { get; set; } = true;
}
public sealed class AiPlanRevision
{
    public int Revision { get; set; }
    public string Content { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
}
public sealed class AiNote
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string SpecialistId { get; set; } = "";
    public string Content { get; set; } = "";
    public string Status { get; set; } = "proposed";
    public string Origin { get; set; } = "user";
    public List<string> SourceMessageIds { get; set; } = new();
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
}
public sealed class AiRun
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string Question { get; set; } = "";
    public string Purpose { get; set; } = "discussion";
    public int PlanRevision { get; set; }
    public int Rounds { get; set; } = 1;
    public List<string> SpecialistIds { get; set; } = new();
    public string Status { get; set; } = "queued";
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? FinishedAt { get; set; }
    public double GenerationSeconds { get; set; }
    public double ObservedRamGb { get; set; }
    public double ObservedVramGb { get; set; }
    public int CompletedTurns { get; set; }
    public int? QualityScore { get; set; }
    public int Interventions { get; set; }
    public string Review { get; set; } = "";
}
public sealed class AiProject
{
    public int Revision { get; set; }
    public string Goal { get; set; } = "";
    public List<AiMember> Members { get; set; } = new();
    public List<AiPlanRevision> Plans { get; set; } = new();
    public List<AiNote> Notes { get; set; } = new();
    public List<AiRun> Runs { get; set; } = new();
}
public sealed class AiProjectEdit
{
    public int Revision { get; set; }
    public string Title { get; set; } = "";
    public string Goal { get; set; } = "";
    public string Plan { get; set; } = "";
    public List<AiMember> Members { get; set; } = new();
}
public sealed class AiRunRequest
{
    public string RequestId { get; set; } = "";
    public string Question { get; set; } = "";
    public string Purpose { get; set; } = "discussion";
    public int Rounds { get; set; } = 1;
    public List<string> SpecialistIds { get; set; } = new();
}
public sealed class AiContextReport
{
    public int EstimatedBytes { get; set; }
    public int OmittedMessages { get; set; }
    public List<string> ExcerptMessageIds { get; set; } = new();
    public List<string> Sources { get; set; } = new();
    public List<string> MessageIds { get; set; } = new();
}
