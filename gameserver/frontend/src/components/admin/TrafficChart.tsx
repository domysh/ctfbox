import { AreaChart, BarChart, LineChart } from "@mantine/charts";
import { Group, SegmentedControl, Text } from "@mantine/core";
import { useMemo } from "react";
import { TrafficPoint } from "../../scripts/admin";
import { hashedColor } from "../../scripts/utils";

export type TrafficMetric = "bytes" | "packets" | "conns";
export type TrafficShape = "stacked" | "area" | "bar" | "line";

export const METRICS = [
    { value: "bytes", label: "Traffic" },
    { value: "packets", label: "Packets" },
    { value: "conns", label: "Connections" },
];

export const SHAPES = [
    { value: "stacked", label: "Stacked" },
    { value: "area", label: "Area" },
    { value: "bar", label: "Bars" },
    { value: "line", label: "Lines" },
];

const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"];

/** Picks one unit for the whole chart from its largest value, so the axis and
 *  the tooltip agree and the numbers stay small. */
const byteScale = (peak: number) => {
    let step = 0;
    while (peak >= 1024 && step < BYTE_UNITS.length - 1) {
        peak /= 1024;
        step++;
    }
    return { divisor: 1024 ** step, unit: BYTE_UNITS[step] };
};

const compact = (value: number) => {
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
    if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
    return String(Math.round(value));
};

export const TrafficChart = ({
    points,
    metric,
    shape,
    teamName,
    height = 320,
}: {
    points: TrafficPoint[];
    metric: TrafficMetric;
    shape: TrafficShape;
    teamName: (id: number) => string;
    height?: number;
}) => {
    const { chartData, series, unit, divisor } = useMemo(() => {
        const buckets = new Map<string, Record<string, number | string>>();
        const teams = new Set<number>();
        let peakStacked = 0;

        for (const point of points) {
            const row = buckets.get(point.at) ?? {
                at: new Date(point.at).toLocaleTimeString(),
            };
            const key = `t${point.team}`;
            row[key] = Number(row[key] ?? 0) + point[metric];
            buckets.set(point.at, row);
            teams.add(point.team);
        }
        for (const row of buckets.values()) {
            const total = Object.entries(row)
                .filter(([key]) => key !== "at")
                .reduce((acc, [, value]) => acc + Number(value), 0);
            peakStacked = Math.max(peakStacked, total);
        }

        const scale =
            metric === "bytes"
                ? byteScale(peakStacked)
                : { divisor: 1, unit: metric === "conns" ? "conn" : "pkt" };

        const rows = [...buckets.entries()]
            .sort((a, b) => a[0].localeCompare(b[0]))
            .map(([, row]) => {
                if (scale.divisor === 1) return row;
                const scaled: Record<string, number | string> = { at: row.at };
                for (const [key, value] of Object.entries(row)) {
                    if (key !== "at")
                        scaled[key] = Number(value) / scale.divisor;
                }
                return scaled;
            });

        return {
            chartData: rows,
            unit: scale.unit,
            divisor: scale.divisor,
            series: [...teams]
                .sort((a, b) => a - b)
                .map((team) => ({
                    name: `t${team}`,
                    label: teamName(team),
                    color: hashedColor(String(team)),
                })),
        };
    }, [points, metric, teamName]);

    if (chartData.length === 0) {
        return (
            <Text c="dimmed" mt="md">
                No traffic recorded yet. Traffic monitoring must be enabled on
                the routers (traffic_monitor in config.json).
            </Text>
        );
    }

    const formatter = (value: number) =>
        divisor === 1
            ? `${compact(value)} ${unit}`
            : `${value.toFixed(value < 10 ? 2 : 1)} ${unit}`;

    const common = {
        h: height,
        mt: "md" as const,
        data: chartData,
        dataKey: "at",
        series,
        yAxisLabel: unit,
        withLegend: true,
        valueFormatter: formatter,
    };

    if (shape === "bar") {
        return <BarChart {...common} type="stacked" />;
    }
    if (shape === "line") {
        return <LineChart {...common} curveType="linear" />;
    }
    // "area" draws the same series without piling them up, which is the only
    // way to compare two teams that are both busy.
    return (
        <AreaChart
            {...common}
            type={shape === "stacked" ? "stacked" : "default"}
            fillOpacity={shape === "stacked" ? 0.6 : 0.25}
            curveType="linear"
        />
    );
};

export const TrafficChartControls = ({
    metric,
    setMetric,
    shape,
    setShape,
}: {
    metric: TrafficMetric;
    setMetric: (value: TrafficMetric) => void;
    shape: TrafficShape;
    setShape: (value: TrafficShape) => void;
}) => (
    <Group gap="xs">
        <SegmentedControl
            size="xs"
            data={METRICS}
            value={metric}
            onChange={(value) => setMetric(value as TrafficMetric)}
        />
        <SegmentedControl
            size="xs"
            data={SHAPES}
            value={shape}
            onChange={(value) => setShape(value as TrafficShape)}
        />
    </Group>
);
