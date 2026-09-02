import { BarChart } from "@mantine/charts";
import {
    Badge,
    Card,
    Group,
    NumberInput,
    Progress,
    Select,
    SimpleGrid,
    Stack,
    Table,
    Text,
    Title,
} from "@mantine/core";
import { useMemo, useState } from "react";
import {
    useAdminServices,
    useSubmissionStats,
    useSubmissions,
} from "../../scripts/admin";
import { useStatusQuery } from "../../scripts/query";

// Why a submission was refused, in the order an organizer cares about.
const REASON_COLORS: Record<string, string> = {
    accepted: "green",
    duplicate: "yellow",
    own: "orange",
    expired: "grape",
    invalid: "red",
    nop: "gray",
    banned: "dark",
    "rate-limited": "blue",
    error: "pink",
};

const REASONS = [
    "accepted",
    "duplicate",
    "own",
    "expired",
    "invalid",
    "nop",
    "banned",
    "rate-limited",
    "error",
];

const percent = (part: number, total: number) =>
    total === 0 ? 0 : Math.round((part / total) * 1000) / 10;

export const SubmissionsPanel = () => {
    const status = useStatusQuery();
    const services = useAdminServices();
    const [team, setTeam] = useState<string | null>("");
    const [victim, setVictim] = useState<string | null>("");
    const [service, setService] = useState<string | null>("");
    const [reason, setReason] = useState<string | null>("");
    const [fromRound, setFromRound] = useState<number | string>("");
    const [toRound, setToRound] = useState<number | string>("");

    const filters = useMemo(
        () => ({
            team: team ?? "",
            victim: victim ?? "",
            service: service ?? "",
            reason: reason ?? "",
            from_round: fromRound === "" ? "" : String(fromRound),
            to_round: toRound === "" ? "" : String(toRound),
        }),
        [team, victim, service, reason, fromRound, toRound],
    );

    const list = useSubmissions(filters);
    const stats = useSubmissionStats(filters);

    const teamName = useMemo(() => {
        const map = new Map<number, string>();
        for (const entry of status.data?.teams ?? [])
            map.set(entry.id, entry.name);
        return (id: number) => (id < 0 ? "-" : map.get(id) ?? `Team ${id}`);
    }, [status.data]);

    const teamOptions = (status.data?.teams ?? []).map((entry) => ({
        value: String(entry.id),
        label: `${entry.id} — ${entry.name}`,
    }));

    const totals = useMemo(() => {
        const reasons = stats.data?.reasons ?? [];
        const total = reasons.reduce((acc, row) => acc + row.count, 0);
        const accepted =
            reasons.find((row) => row.reason === "accepted")?.count ?? 0;
        return { total, accepted };
    }, [stats.data]);

    const roundSeries = useMemo(
        () =>
            (stats.data?.rounds ?? []).slice(-120).map((row) => ({
                round: String(row.round),
                accepted: row.accepted,
                refused: row.total - row.accepted,
            })),
        [stats.data],
    );

    return (
        <Stack gap="lg">
            <Card withBorder padding="md">
                <Title order={4}>Submissions</Title>
                <Text size="sm" c="dimmed">
                    Every attempt, accepted or not. The refusals are the
                    interesting half: they say whether a team is replaying old
                    flags, submitting its own, or simply guessing.
                </Text>
                <Group mt="sm" align="end" gap="sm">
                    <Select
                        size="xs"
                        w={200}
                        label="Attacker"
                        placeholder="every team"
                        clearable
                        searchable
                        data={teamOptions}
                        value={team}
                        onChange={setTeam}
                    />
                    <Select
                        size="xs"
                        w={200}
                        label="Victim"
                        placeholder="every team"
                        clearable
                        searchable
                        data={teamOptions}
                        value={victim}
                        onChange={setVictim}
                    />
                    <Select
                        size="xs"
                        w={180}
                        label="Service"
                        placeholder="every service"
                        clearable
                        data={(services.data ?? []).map((s) => s.name)}
                        value={service}
                        onChange={setService}
                    />
                    <Select
                        size="xs"
                        w={160}
                        label="Outcome"
                        placeholder="any"
                        clearable
                        data={REASONS}
                        value={reason}
                        onChange={setReason}
                    />
                    <NumberInput
                        size="xs"
                        w={110}
                        min={0}
                        label="From round"
                        value={fromRound}
                        onChange={setFromRound}
                    />
                    <NumberInput
                        size="xs"
                        w={110}
                        min={0}
                        label="To round"
                        value={toRound}
                        onChange={setToRound}
                    />
                </Group>
            </Card>

            <SimpleGrid cols={{ base: 1, md: 2 }}>
                <Card withBorder padding="md">
                    <Title order={5}>Outcomes</Title>
                    <Text size="sm" c="dimmed">
                        {totals.total} attempts, {totals.accepted} accepted (
                        {percent(totals.accepted, totals.total)}%)
                    </Text>
                    <Stack gap="xs" mt="sm">
                        {(stats.data?.reasons ?? []).map((row) => (
                            <div key={row.reason}>
                                <Group justify="space-between" gap="xs">
                                    <Badge
                                        size="sm"
                                        variant="light"
                                        color={
                                            REASON_COLORS[row.reason] ?? "gray"
                                        }
                                    >
                                        {row.reason}
                                    </Badge>
                                    <Text size="sm">
                                        {row.count} (
                                        {percent(row.count, totals.total)}%)
                                    </Text>
                                </Group>
                                <Progress
                                    mt={4}
                                    size="sm"
                                    value={percent(row.count, totals.total)}
                                    color={REASON_COLORS[row.reason] ?? "gray"}
                                />
                            </div>
                        ))}
                        {(stats.data?.reasons ?? []).length === 0 && (
                            <Text c="dimmed">Nothing submitted yet.</Text>
                        )}
                    </Stack>
                </Card>

                <Card withBorder padding="md">
                    <Title order={5}>Per team</Title>
                    <Table mt="sm" verticalSpacing="xs" striped>
                        <Table.Thead>
                            <Table.Tr>
                                <Table.Th>Team</Table.Th>
                                <Table.Th>Attempts</Table.Th>
                                <Table.Th>Accepted</Table.Th>
                                <Table.Th>Hit rate</Table.Th>
                                <Table.Th>Points</Table.Th>
                            </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                            {(stats.data?.teams ?? []).map((row) => (
                                <Table.Tr key={row.team_id}>
                                    <Table.Td>{teamName(row.team_id)}</Table.Td>
                                    <Table.Td>{row.total}</Table.Td>
                                    <Table.Td>{row.accepted}</Table.Td>
                                    <Table.Td>
                                        {percent(row.accepted, row.total)}%
                                    </Table.Td>
                                    <Table.Td>
                                        {row.points.toFixed(1)}
                                    </Table.Td>
                                </Table.Tr>
                            ))}
                            {(stats.data?.teams ?? []).length === 0 && (
                                <Table.Tr>
                                    <Table.Td colSpan={5}>
                                        <Text c="dimmed">No data.</Text>
                                    </Table.Td>
                                </Table.Tr>
                            )}
                        </Table.Tbody>
                    </Table>
                </Card>
            </SimpleGrid>

            <Card withBorder padding="md">
                <Title order={5}>Per round</Title>
                {roundSeries.length === 0 ? (
                    <Text c="dimmed" mt="sm">
                        No data.
                    </Text>
                ) : (
                    <BarChart
                        h={240}
                        mt="md"
                        data={roundSeries}
                        dataKey="round"
                        type="stacked"
                        withLegend
                        series={[
                            { name: "accepted", color: "green.6" },
                            { name: "refused", color: "red.6" },
                        ]}
                    />
                )}
            </Card>

            <Card withBorder padding="md">
                <Group justify="space-between">
                    <Title order={5}>Latest attempts</Title>
                    <Text size="sm" c="dimmed">
                        showing {list.data?.events.length ?? 0} of{" "}
                        {list.data?.total ?? 0}
                    </Text>
                </Group>
                <Table.ScrollContainer minWidth={900}>
                    <Table striped highlightOnHover mt="sm" verticalSpacing="xs">
                        <Table.Thead>
                            <Table.Tr>
                                <Table.Th>Time</Table.Th>
                                <Table.Th>Round</Table.Th>
                                <Table.Th>Attacker</Table.Th>
                                <Table.Th>Victim</Table.Th>
                                <Table.Th>Service</Table.Th>
                                <Table.Th>Flag</Table.Th>
                                <Table.Th>Outcome</Table.Th>
                                <Table.Th>Points</Table.Th>
                            </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                            {(list.data?.events ?? []).map((event) => (
                                <Table.Tr key={event.id}>
                                    <Table.Td>
                                        {new Date(
                                            event.at,
                                        ).toLocaleTimeString()}
                                    </Table.Td>
                                    <Table.Td>{event.round}</Table.Td>
                                    <Table.Td>
                                        {teamName(event.team_id)}
                                    </Table.Td>
                                    <Table.Td>
                                        {teamName(event.victim_id)}
                                    </Table.Td>
                                    <Table.Td>{event.service || "-"}</Table.Td>
                                    <Table.Td>
                                        <Text size="xs" ff="monospace">
                                            {event.flag || "-"}
                                        </Text>
                                    </Table.Td>
                                    <Table.Td>
                                        <Badge
                                            size="sm"
                                            variant="light"
                                            color={
                                                REASON_COLORS[event.reason] ??
                                                "gray"
                                            }
                                        >
                                            {event.reason}
                                        </Badge>
                                    </Table.Td>
                                    <Table.Td>
                                        {event.points
                                            ? event.points.toFixed(2)
                                            : "-"}
                                    </Table.Td>
                                </Table.Tr>
                            ))}
                            {(list.data?.events ?? []).length === 0 && (
                                <Table.Tr>
                                    <Table.Td colSpan={8}>
                                        <Text c="dimmed">
                                            Nothing matches these filters.
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
