import {
    Badge,
    Card,
    Group,
    SegmentedControl,
    Stack,
    Table,
    Text,
    Title,
} from "@mantine/core";
import { useMemo, useState } from "react";
import {
    formatBytes,
    useAttackGraph,
    useTraffic,
    useTrafficMatrix,
} from "../../scripts/admin";
import { useStatusQuery } from "../../scripts/query";
import { PcapPanel } from "./PcapPanel";
import { VpnProfilesPanel } from "./VpnProfilesPanel";
import {
    TrafficChart,
    TrafficChartControls,
    TrafficMetric,
    TrafficShape,
} from "./TrafficChart";

const WINDOWS = [
    { value: "15", label: "15 min" },
    { value: "60", label: "1 h" },
    { value: "240", label: "4 h" },
    { value: "720", label: "12 h" },
];

export const MonitoringPanel = () => {
    const [window, setWindow] = useState("60");
    const [metric, setMetric] = useState<TrafficMetric>("bytes");
    const [shape, setShape] = useState<TrafficShape>("stacked");
    const minutes = Number(window);
    const traffic = useTraffic(minutes);
    const matrix = useTrafficMatrix(minutes);
    const attacks = useAttackGraph();
    const status = useStatusQuery();

    const teamName = useMemo(() => {
        const map = new Map<number, string>();
        for (const team of status.data?.teams ?? []) map.set(team.id, team.name);
        return (id: number) => map.get(id) ?? `Team ${id}`;
    }, [status.data]);

    const topEdges = (matrix.data?.edges ?? []).slice(0, 40);
    const topAttacks = [...(attacks.data ?? [])]
        .sort((a, b) => b.flags - a.flags)
        .slice(0, 40);

    return (
        <Stack gap="lg">
            <Card withBorder padding="md">
                <Group justify="space-between">
                    <Group>
                        <Title order={4}>Traffic per team</Title>
                        <SegmentedControl
                            data={WINDOWS}
                            value={window}
                            onChange={setWindow}
                            size="xs"
                        />
                    </Group>
                    <TrafficChartControls
                        metric={metric}
                        setMetric={setMetric}
                        shape={shape}
                        setShape={setShape}
                    />
                </Group>
                <Text size="sm" c="dimmed">
                    Counted on every router of the deployment, per source team.
                    Connections are new flows opened, which tracks attack
                    attempts far better than the raw packet count.
                </Text>
                <TrafficChart
                    points={traffic.data?.points ?? []}
                    metric={metric}
                    shape={shape}
                    teamName={teamName}
                />
            </Card>

            <VpnProfilesPanel minutes={minutes} />

            <Card withBorder padding="md">
                <Title order={4}>Who is talking to whom</Title>
                <Text size="sm" c="dimmed">
                    Network level view over the last {matrix.data?.minutes ?? minutes}{" "}
                    minutes. `vpn` is traffic coming from a player tunnel, `vm`
                    is traffic coming from a vulnbox.
                </Text>
                <Table.ScrollContainer minWidth={600}>
                    <Table striped highlightOnHover mt="sm" verticalSpacing="xs">
                        <Table.Thead>
                            <Table.Tr>
                                <Table.Th>From</Table.Th>
                                <Table.Th>To</Table.Th>
                                <Table.Th>Kind</Table.Th>
                                <Table.Th>Volume</Table.Th>
                                <Table.Th>Packets</Table.Th>
                                <Table.Th>Connections</Table.Th>
                            </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                            {topEdges.map((edge, index) => (
                                <Table.Tr key={index}>
                                    <Table.Td>{teamName(edge.src_team)}</Table.Td>
                                    <Table.Td>{teamName(edge.dst_team)}</Table.Td>
                                    <Table.Td>
                                        <Badge
                                            size="sm"
                                            variant="light"
                                            color={
                                                edge.kind === "vpn"
                                                    ? "cyan"
                                                    : "grape"
                                            }
                                        >
                                            {edge.kind}
                                        </Badge>
                                    </Table.Td>
                                    <Table.Td>{formatBytes(edge.bytes)}</Table.Td>
                                    <Table.Td>{edge.packets}</Table.Td>
                                    <Table.Td>{edge.conns}</Table.Td>
                                </Table.Tr>
                            ))}
                            {topEdges.length === 0 && (
                                <Table.Tr>
                                    <Table.Td colSpan={6}>
                                        <Text c="dimmed">No samples yet.</Text>
                                    </Table.Td>
                                </Table.Tr>
                            )}
                        </Table.Tbody>
                    </Table>
                </Table.ScrollContainer>
            </Card>

            <PcapPanel />

            <Card withBorder padding="md">
                <Title order={4}>Attack graph</Title>
                <Text size="sm" c="dimmed">
                    Built from the accepted flags: the ground truth of who is
                    actually breaking whom.
                </Text>
                <Table.ScrollContainer minWidth={600}>
                    <Table striped highlightOnHover mt="sm" verticalSpacing="xs">
                        <Table.Thead>
                            <Table.Tr>
                                <Table.Th>Attacker</Table.Th>
                                <Table.Th>Victim</Table.Th>
                                <Table.Th>Service</Table.Th>
                                <Table.Th>Flags</Table.Th>
                                <Table.Th>Points</Table.Th>
                            </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                            {topAttacks.map((edge, index) => (
                                <Table.Tr key={index}>
                                    <Table.Td>{teamName(edge.from_team)}</Table.Td>
                                    <Table.Td>{teamName(edge.to_team)}</Table.Td>
                                    <Table.Td>{edge.service}</Table.Td>
                                    <Table.Td>{edge.flags}</Table.Td>
                                    <Table.Td>{edge.points.toFixed(1)}</Table.Td>
                                </Table.Tr>
                            ))}
                            {topAttacks.length === 0 && (
                                <Table.Tr>
                                    <Table.Td colSpan={5}>
                                        <Text c="dimmed">
                                            No flag stolen yet.
                                        </Text>
                                    </Table.Td>
                                </Table.Tr>
                            )}
                        </Table.Tbody>
                    </Table>
                </Table.ScrollContainer>
            </Card>
        </Stack>
    );
};
