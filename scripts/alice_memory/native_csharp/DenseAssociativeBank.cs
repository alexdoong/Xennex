using System;

namespace Xennex.Alice.Experimental;

/// <summary>Dense online RLS weights and inverse covariance, with no example buffer.</summary>
internal sealed class DenseAssociativeBank
{
    private double[] weights;
    private double[] precision;
    private double[] nextWeights;
    private double[] nextPrecision;
    private readonly double[] projected;
    private readonly double[] error;

    public int KeySize { get; }
    public int ValueSize { get; }
    public long Writes { get; private set; }
    public long StateBytes => ((long)weights.Length + precision.Length) * sizeof(double) + sizeof(long);
    public long ScratchBytes => ((long)nextWeights.Length + nextPrecision.Length + projected.Length + error.Length) * sizeof(double);

    public DenseAssociativeBank(int keySize, int valueSize)
    {
        if (keySize is < 1 or > 256 || valueSize is < 1 or > 32)
            throw new ArgumentOutOfRangeException(nameof(keySize), "Invalid native bank dimensions.");
        KeySize = keySize;
        ValueSize = valueSize;
        weights = new double[keySize * valueSize];
        precision = new double[keySize * keySize];
        nextWeights = new double[weights.Length];
        nextPrecision = new double[precision.Length];
        projected = new double[keySize];
        error = new double[valueSize];
        for (int index = 0; index < keySize; index++)
            precision[index * keySize + index] = 1000;
    }

    public void Write(ReadOnlySpan<double> key, ReadOnlySpan<double> value, double strength = 1)
    {
        Validate(key, KeySize);
        Validate(value, ValueSize);
        if (!double.IsFinite(strength) || strength is <= 0 or > 10000 || Writes >= 100000)
            throw new ArgumentOutOfRangeException(nameof(strength), "Invalid native write strength/budget.");
        Project(key);
        double denominator = 1 / strength + Dot(key, projected);
        if (!double.IsFinite(denominator) || denominator <= 0)
            throw new ArgumentException("Native covariance/write overflow.");
        for (int row = 0; row < ValueSize; row++)
            error[row] = value[row] - Dot(weights.AsSpan(row * KeySize, KeySize), key);
        for (int row = 0; row < ValueSize; row++)
            UpdateWeightRow(row, denominator);
        for (int row = 0; row < KeySize; row++)
            UpdatePrecisionRow(row, denominator);
        for (int row = 0; row < KeySize; row++)
            SymmetrizeRow(row);
        // Commit only a completely finite candidate, retaining previous state on failure.
        Validate(nextWeights, weights.Length);
        Validate(nextPrecision, precision.Length);
        (weights, nextWeights) = (nextWeights, weights);
        (precision, nextPrecision) = (nextPrecision, precision);
        Writes++;
    }

    private void UpdateWeightRow(int row, double denominator)
    {
        int offset = row * KeySize;
        for (int column = 0; column < KeySize; column++)
            nextWeights[offset + column] = weights[offset + column] + error[row] * (projected[column] / denominator);
    }

    private void UpdatePrecisionRow(int row, double denominator)
    {
        int offset = row * KeySize;
        for (int column = 0; column < KeySize; column++)
            nextPrecision[offset + column] = precision[offset + column] - projected[row] * projected[column] / denominator;
    }

    private void SymmetrizeRow(int row)
    {
        for (int column = row + 1; column < KeySize; column++)
        {
            double mean = (nextPrecision[row * KeySize + column] + nextPrecision[column * KeySize + row]) * .5;
            nextPrecision[row * KeySize + column] = mean;
            nextPrecision[column * KeySize + row] = mean;
        }
    }

    public void Read(ReadOnlySpan<double> key, Span<double> value)
    {
        Validate(key, KeySize);
        if (value.Length != ValueSize)
            throw new ArgumentException("Invalid native read destination.");
        for (int row = 0; row < ValueSize; row++)
            value[row] = Dot(weights.AsSpan(row * KeySize, KeySize), key);
    }

    public double Variance(ReadOnlySpan<double> key)
    {
        Validate(key, KeySize);
        Project(key);
        return Dot(key, projected);
    }

    private void Project(ReadOnlySpan<double> key)
    {
        for (int row = 0; row < KeySize; row++)
            projected[row] = Dot(precision.AsSpan(row * KeySize, KeySize), key);
    }

    private static double Dot(ReadOnlySpan<double> left, ReadOnlySpan<double> right)
    {
        double total = 0;
        for (int index = 0; index < left.Length; index++)
            total += left[index] * right[index];
        return total;
    }

    public BankState Snapshot() => new(KeySize, ValueSize, (double[])weights.Clone(), (double[])precision.Clone(), Writes);

    public static DenseAssociativeBank Restore(BankState state)
    {
        ArgumentNullException.ThrowIfNull(state);
        ArgumentNullException.ThrowIfNull(state.Weights);
        ArgumentNullException.ThrowIfNull(state.Precision);
        DenseAssociativeBank bank = new(state.KeySize, state.ValueSize);
        Validate(state.Weights, bank.weights.Length);
        Validate(state.Precision, bank.precision.Length);
        if (state.Writes is < 0 or > 100000)
            throw new ArgumentException("Invalid native write count.");
        for (int row = 0; row < bank.KeySize; row++)
            ValidateSymmetryRow(state.Precision, bank.KeySize, row);
        ValidatePositiveDefinite(state.Precision, bank.KeySize);
        state.Weights.CopyTo(bank.weights, 0);
        state.Precision.CopyTo(bank.precision, 0);
        bank.Writes = state.Writes;
        return bank;
    }

    private static void ValidateSymmetryRow(double[] matrix, int size, int row)
    {
        for (int column = 0; column < size; column++)
            if (Math.Abs(matrix[row * size + column] - matrix[column * size + row]) > 1e-8)
                throw new ArgumentException("Native precision is not symmetric.");
    }

    private static void ValidatePositiveDefinite(double[] matrix, int size)
    {
        double[] lower = new double[matrix.Length];
        for (int row = 0; row < size; row++)
            CholeskyRow(matrix, lower, size, row);
    }

    private static void CholeskyRow(double[] matrix, double[] lower, int size, int row)
    {
        for (int column = 0; column <= row; column++)
        {
            double sum = matrix[row * size + column];
            for (int index = 0; index < column; index++)
                sum -= lower[row * size + index] * lower[column * size + index];
            if (row == column && (!double.IsFinite(sum) || sum <= 0))
                throw new ArgumentException("Native precision is not positive definite.");
            lower[row * size + column] = row == column ? Math.Sqrt(sum) : sum / lower[column * size + column];
        }
    }

    private static void Validate(ReadOnlySpan<double> values, int expected)
    {
        if (values.Length != expected)
            throw new ArgumentException("Invalid native vector/matrix length.");
        foreach (double value in values)
            if (!double.IsFinite(value))
                throw new ArgumentException("Native data must be finite.");
    }
}

internal sealed record BankState(int KeySize, int ValueSize, double[] Weights, double[] Precision, long Writes);
