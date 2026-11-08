using System.Diagnostics;
using System.Text.Json;
using Xennex.Alice.Experimental;

internal static class Program
{
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        UnmappedMemberHandling = System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow
    };

    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 1 && args[0] == "--self-test")
            {
                SelfTest();
                return 0;
            }
            if (args.Length != 2)
                throw new ArgumentException("Usage: AliceRuntimeTests fixture.json output.json | --self-test");
            FileInfo file = new(args[0]);
            if (file.Length > 16 * 1024 * 1024)
                throw new ArgumentException("Fixture exceeds 16 MiB.");
            Fixture input = JsonSerializer.Deserialize<Fixture>(File.ReadAllBytes(file.FullName), Json)
                ?? throw new ArgumentException("Missing fixture.");
            if (input.Format != 1 || input.Banks is null || input.Banks.Length is < 1 or > 64)
                throw new ArgumentException("Invalid fixture.");
            if (input.Banks.Sum(bank => bank.Steps?.Length ?? 0) > 10000)
                throw new ArgumentException("Fixture exceeds update budget.");
            CaseResult[] results = input.Banks.Select(Evaluate).ToArray();
            using Process process = Process.GetCurrentProcess();
            process.Refresh();
            File.WriteAllBytes(args[1], JsonSerializer.SerializeToUtf8Bytes(new
            {
                format = 1, banks = results, processCpuSeconds = process.TotalProcessorTime.TotalSeconds,
                processPeakRssBytes = process.PeakWorkingSet64,
                runtime = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription
            }, Json));
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine($"Native Alice experiment: {error.GetType().Name}: {error.Message}");
            return 1;
        }
    }

    private static CaseResult Evaluate(BankCase input)
    {
        if (input.Initial is null || input.Steps is null || input.Queries is null || input.Name is null)
            throw new ArgumentException("Incomplete bank case.");
        if (input.Steps.Length is < 1 or > 10000 || input.Queries.Length is < 1 or > 256)
            throw new ArgumentException("Invalid case budget.");
        DenseAssociativeBank bank = DenseAssociativeBank.Restore(input.Initial);
        foreach (Step step in input.Steps)
            bank.Write(step.Key, step.Value, step.Strength);
        Probe[] probes = input.Queries.Select(key => Read(bank, key)).ToArray();
        BankState state = bank.Snapshot();
        DenseAssociativeBank restored = DenseAssociativeBank.Restore(state);
        Step next = input.Steps[0];
        bank.Write(next.Key, next.Value, next.Strength);
        restored.Write(next.Key, next.Value, next.Strength);
        BankState resumed = restored.Snapshot();
        BankState uninterrupted = bank.Snapshot();
        if (!resumed.Weights.SequenceEqual(uninterrupted.Weights) || !resumed.Precision.SequenceEqual(uninterrupted.Precision))
            throw new InvalidOperationException("Checkpoint changed the next update.");
        return new(input.Name, state, resumed, probes, Benchmark(input));
    }

    private static Probe Read(DenseAssociativeBank bank, double[] key)
    {
        double[] value = new double[bank.ValueSize];
        bank.Read(key, value);
        return new(value, bank.Variance(key));
    }

    private static Measurement Benchmark(BankCase input)
    {
        DenseAssociativeBank warm = DenseAssociativeBank.Restore(input.Initial);
        double[] warmRead = new double[warm.ValueSize];
        foreach (Step step in input.Steps)
        {
            warm.Write(step.Key, step.Value, step.Strength);
            warm.Read(step.Key, warmRead);
            warm.Variance(step.Key);
        }
        List<double> timings = new(input.Steps.Length * 3);
        long allocated = 0;
        double totalSeconds = 0;
        for (int repetition = 0; repetition < 3; repetition++)
        {
            DenseAssociativeBank bank = DenseAssociativeBank.Restore(input.Initial);
            double[] read = new double[bank.ValueSize];
            long before = GC.GetAllocatedBytesForCurrentThread();
            long started = Stopwatch.GetTimestamp();
            foreach (Step step in input.Steps)
            {
                long tick = Stopwatch.GetTimestamp();
                bank.Write(step.Key, step.Value, step.Strength);
                bank.Read(step.Key, read);
                bank.Variance(step.Key);
                timings.Add(Stopwatch.GetElapsedTime(tick).TotalMilliseconds);
            }
            totalSeconds += Stopwatch.GetElapsedTime(started).TotalSeconds;
            allocated += GC.GetAllocatedBytesForCurrentThread() - before;
            if (totalSeconds > 120)
                throw new InvalidOperationException("Native kernel exceeded 120 s.");
        }
        double[] ordered = timings.Order().ToArray();
        return new(timings.Count, Percentile(ordered, .5), Percentile(ordered, .95),
            Percentile(ordered, .99), totalSeconds, allocated, warm.StateBytes, warm.ScratchBytes);
    }

    private static double Percentile(double[] values, double quantile) => values[(int)Math.Ceiling(quantile * values.Length) - 1];

    private static void SelfTest()
    {
        DenseAssociativeBank bank = new(2, 1);
        bank.Write(new double[] { 1, 0 }, new double[] { 2 }, 1);
        double[] read = new double[1];
        bank.Read(new double[] { 1, 0 }, read);
        if (Math.Abs(read[0] - 2000.0 / 1001) > 1e-12)
            throw new InvalidOperationException("Independent one-step ridge oracle failed.");
        BankState before = bank.Snapshot();
        Reject(() => bank.Write(new double[] { 1 }, new double[] { 2 }));
        Reject(() => bank.Write(new double[] { double.NaN, 0 }, new double[] { 2 }));
        Reject(() => bank.Write(new double[] { 1, 0 }, new double[] { double.PositiveInfinity }));
        Reject(() => bank.Write(new double[] { 1, 0 }, new double[] { 2 }, 0));
        Reject(() => bank.Write(new double[] { 1, 0 }, new double[] { 2 }, 10001));
        Reject(() => bank.Write(new double[] { double.MaxValue, double.MaxValue }, new double[] { 2 }));
        Reject(() => bank.Write(new double[] { 0, .0001 }, new double[] { double.MaxValue }, 10000));
        if (!before.Weights.SequenceEqual(bank.Snapshot().Weights) || !before.Precision.SequenceEqual(bank.Snapshot().Precision) || before.Writes != bank.Writes)
            throw new InvalidOperationException("Rejected write changed committed state.");
        Reject(() => DenseAssociativeBank.Restore(before with { Writes = -1 }));
        Reject(() => DenseAssociativeBank.Restore(before with { Weights = null! }));
        Reject(() => DenseAssociativeBank.Restore(before with { Weights = new double[0] }));
        Reject(() => DenseAssociativeBank.Restore(before with { Precision = new double[] { 1, 1, 0, 1 } }));
        Reject(() => DenseAssociativeBank.Restore(before with { Precision = new double[] { 1, 0, 0, -1 } }));
        DenseAssociativeBank restored = DenseAssociativeBank.Restore(before);
        before.Weights[0] = 42;
        if (restored.Snapshot().Weights[0] == 42 || bank.Snapshot().Weights[0] == 42)
            throw new InvalidOperationException("Checkpoint arrays share storage.");
        bank.Write(new double[] { 0, 1 }, new double[] { 3 }, .4);
        restored.Write(new double[] { 0, 1 }, new double[] { 3 }, .4);
        if (!bank.Snapshot().Weights.SequenceEqual(restored.Snapshot().Weights))
            throw new InvalidOperationException("Restored next update diverged.");
        Console.WriteLine("Native RLS self-tests passed: ridge oracle, rejection atomicity, checkpoint validation, independent storage and next update.");
    }

    private static void Reject(Action action)
    {
        try { action(); }
        catch (ArgumentException) { return; }
        throw new InvalidOperationException("Invalid input was accepted.");
    }
}

internal sealed record Fixture(int Format, BankCase[] Banks);
internal sealed record BankCase(string Name, BankState Initial, Step[] Steps, double[][] Queries);
internal sealed record Step(double[] Key, double[] Value, double Strength);
internal sealed record Probe(double[] Value, double Variance);
internal sealed record Measurement(int Operations, double P50Ms, double P95Ms, double P99Ms, double Seconds,
    long AllocatedBytes, long StateBytes, long ScratchBytes);
internal sealed record CaseResult(string Name, BankState State, BankState Resumed, Probe[] Probes, Measurement Measurement);
