using System;
using System.Collections.Generic;

namespace Xennex.Models.LocalAi;

public sealed class AiSettings
{
    public string Provider { get; set; } = "compatible";
    public bool AutoBudget { get; set; }
    public int ContextTokens { get; set; } = 4096;
    public int KeepAliveSeconds { get; set; } = 60;
    public string Endpoint { get; set; } = "http://127.0.0.1:1234/v1";
    public string Model { get; set; } = "";
    public int MemoryLimitPercent { get; set; } = 75;
    public double AdditionalRamGb { get; set; } = 4;
    public double AdditionalVramGb { get; set; } = 8;
    public bool UseGpu { get; set; } = true;
    public int MaxOutputTokens { get; set; } = 1024;
}

public sealed class AiMessage
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string AuthorId { get; set; } = "";
    public string AuthorName { get; set; } = "";
    public string AuthorRole { get; set; } = "";
    public string Model { get; set; } = "";
    public string RunId { get; set; } = "";
    public string Purpose { get; set; } = "discussion";
    public AiContextReport Context { get; set; }

    public string Role { get; set; } = "user";
    public string Content { get; set; } = "";
    public string Status { get; set; } = "complete";
    public string Detail { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
}

public sealed class AiChat
{
    public AiProject Project { get; set; }

    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string Title { get; set; } = "Nova conversa";
    public string Model { get; set; } = "";
    public List<AiMessage> Messages { get; set; } = new();
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
}

public sealed class AiLibrary
{
    public int SchemaVersion { get; set; } = 2;
    public AiSettings Settings { get; set; } = new();
    public List<AiChat> Chats { get; set; } = new();
    public List<AiSpecialist> Specialists { get; set; } = new();
    public List<ResourceMeasurement> Measurements { get; set; } = new();
}

public sealed class ResourceSnapshot
{
    public DateTimeOffset CapturedAt { get; set; } = DateTimeOffset.UtcNow;
    public double? RamTotalGb { get; set; }
    public double? RamUsedGb { get; set; }
    public double? VramTotalGb { get; set; }
    public double? VramUsedGb { get; set; }
    public string GpuName { get; set; } = "";
    public string Warning { get; set; } = "";
}

public sealed class AiJob
{
    public string MessageId { get; set; } = "";
    public string RunId { get; set; } = "";
    public AiSpecialist Specialist { get; set; }
    public string Team { get; set; } = "";
    public int Round { get; set; }
    public DateTimeOffset? StartedAt { get; set; }

    public ResourceDemand Demand { get; set; }
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string ChatId { get; set; } = "";
    public string Status { get; set; } = "queued";
    public string Detail { get; set; } = "Na fila";
    public AiSettings Settings { get; set; } = new();
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
}
