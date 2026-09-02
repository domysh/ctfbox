import {
    Alert,
    Badge,
    Box,
    Button,
    Card,
    Group,
    NumberInput,
    SimpleGrid,
    Space,
    Stack,
    Table,
    Text,
    TextInput,
    Title,
} from "@mantine/core";
import { useState } from "react";
import {
    AdminOverview,
    adminSend,
    fromLocalInput,
    toLocalInput,
    useAdminMutation,
} from "../../scripts/admin";

const NETWORK_COLORS: Record<string, string> = {
    unlocked: "green",
    locked: "yellow",
    frozen: "red",
    unknown: "gray",
};

export const OverviewPanel = ({ overview }: { overview: AdminOverview }) => {
    const settings = overview.settings;
    const unhealthy = overview.nodes.filter((node) => !node.alive);
    const [freezeAt, setFreezeAt] = useState(
        toLocalInput(settings.scoreboard_freeze_time),
    );
    const [freezeRound, setFreezeRound] = useState<number | string>(
        overview.round,
    );

    const network = useAdminMutation((action: string) =>
        adminSend(`/network/${action}`, "POST"),
    );
    const freeze = useAdminMutation((body: object) =>
        adminSend("/scoreboard/freeze", "POST", body),
    );
    const pause = useAdminMutation((paused: boolean) =>
        adminSend("/game/pause", "POST", { paused }),
    );
    const reload = useAdminMutation(() => adminSend("/reload", "POST"));

    return (
        <Stack gap="lg">
            {settings.game_paused && (
                <Alert color="orange" title="Game paused">
                    The checkers are stopped and flag submission is refused. The
                    game clock is shifted forward when you resume, so no round
                    is lost.
                </Alert>
            )}
            {unhealthy.length > 0 && (
                <Alert
                    color="red"
                    title={`${unhealthy.length} node(s) not reporting`}
                >
                    {unhealthy.map((node) => node.name).join(", ")} stopped
                    checking in. Their part of the game network cannot be
                    changed from here until they come back, and the teams they
                    host may be unreachable.
                </Alert>
            )}
            {settings.scoreboard_frozen && (
                <Alert color="blue" title="Scoreboard frozen">
                    Players see the ranking of round{" "}
                    {settings.scoreboard_freeze_round}; SLA and service status
                    keep updating live.
                </Alert>
            )}

            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
                <Card withBorder padding="md">
                    <Text size="sm" c="dimmed">
                        Current round
                    </Text>
                    <Title order={2}>{overview.round}</Title>
                    <Text size="xs" c="dimmed">
                        tick {settings.tick_time}s
                    </Text>
                </Card>
                <Card withBorder padding="md">
                    <Text size="sm" c="dimmed">
                        Network
                    </Text>
                    <Badge
                        size="lg"
                        color={
                            NETWORK_COLORS[overview.network_state] ?? "gray"
                        }
                    >
                        {overview.network_state}
                    </Badge>
                    <Space h="xs" />
                    <Text size="xs" c="dimmed">
                        {overview.teams} teams / {overview.services} services
                    </Text>
                </Card>
                <Card withBorder padding="md">
                    <Text size="sm" c="dimmed">
                        Checker capacity
                    </Text>
                    <Title order={2}>{overview.capacity}</Title>
                    <Text size="xs" c="dimmed">
                        {overview.workers.filter((w) => w.alive).length} live
                        worker(s)
                    </Text>
                </Card>
                <Card withBorder padding="md">
                    <Text size="sm" c="dimmed">
                        Queue
                    </Text>
                    <Title order={2}>
                        {overview.queue.running}/{overview.queue.pending}
                    </Title>
                    <Text size="xs" c="dimmed">
                        running / pending
                    </Text>
                </Card>
            </SimpleGrid>

            <Card withBorder padding="md">
                <Title order={4}>Game network</Title>
                <Text size="sm" c="dimmed">
                    Applied on every router of the deployment.
                </Text>
                <Space h="sm" />
                <Group>
                    <Button
                        color="green"
                        loading={network.isPending}
                        onClick={() => network.mutate("unlock")}
                    >
                        Unlock
                    </Button>
                    <Button
                        color="yellow"
                        loading={network.isPending}
                        onClick={() => network.mutate("lock")}
                    >
                        Lock
                    </Button>
                    <Button
                        color="red"
                        loading={network.isPending}
                        onClick={() => network.mutate("freeze")}
                    >
                        Freeze
                    </Button>
                    <Box flex={1} />
                    <Button
                        variant="outline"
                        color={settings.game_paused ? "green" : "orange"}
                        loading={pause.isPending}
                        onClick={() => pause.mutate(!settings.game_paused)}
                    >
                        {settings.game_paused ? "Resume game" : "Pause game"}
                    </Button>
                    <Button
                        variant="subtle"
                        loading={reload.isPending}
                        onClick={() => reload.mutate(undefined as never)}
                    >
                        Reload state
                    </Button>
                </Group>
                {network.isError && (
                    <Text c="red" size="sm" mt="sm">
                        {(network.error as Error).message}
                    </Text>
                )}
            </Card>

            <Card withBorder padding="md">
                <Title order={4}>Scoreboard freeze</Title>
                <Text size="sm" c="dimmed">
                    While frozen the ranking stops at the chosen round: only the
                    SLA and the service status keep moving, so the final
                    standings stay secret until you unfreeze.
                </Text>
                <Space h="sm" />
                <Group align="end">
                    <NumberInput
                        label="Freeze at round"
                        value={freezeRound}
                        onChange={setFreezeRound}
                        min={0}
                        w={160}
                    />
                    <Button
                        loading={freeze.isPending}
                        onClick={() =>
                            freeze.mutate({
                                frozen: true,
                                round: Number(freezeRound),
                            })
                        }
                    >
                        Freeze now
                    </Button>
                    <Button
                        variant="outline"
                        loading={freeze.isPending}
                        onClick={() => freeze.mutate({ frozen: false })}
                    >
                        Unfreeze
                    </Button>
                </Group>
                <Space h="md" />
                <Group align="end">
                    <TextInput
                        type="datetime-local"
                        label="Scheduled freeze"
                        value={freezeAt}
                        onChange={(event) =>
                            setFreezeAt(event.currentTarget.value)
                        }
                        w={260}
                    />
                    <Button
                        variant="light"
                        loading={freeze.isPending}
                        onClick={() =>
                            freeze.mutate({ at: fromLocalInput(freezeAt) })
                        }
                        disabled={!freezeAt}
                    >
                        Schedule
                    </Button>
                </Group>
                <Text size="xs" c="dimmed" mt="xs">
                    The scoreboard freezes on its own at this time, no need to be
                    at the keyboard.
                </Text>
            </Card>

            <Card withBorder padding="md">
                <Group mb={4}>
                    <Title order={4}>Nodes</Title>
                    {unhealthy.length > 0 && (
                        <Badge color="red">
                            {unhealthy.length} not reporting
                        </Badge>
                    )}
                </Group>
                <Text size="sm" c="dimmed">
                    Every router checks in with the control node every few
                    seconds. A node that stops reporting is either down or cut
                    off from the game network, and its rules can no longer be
                    changed from here.
                </Text>
                <Table striped highlightOnHover mt="sm">
                    <Table.Thead>
                        <Table.Tr>
                            <Table.Th>Name</Table.Th>
                            <Table.Th>Roles</Table.Th>
                            <Table.Th>Status</Table.Th>
                            <Table.Th>Address</Table.Th>
                            <Table.Th>Network</Table.Th>
                            <Table.Th>Bans</Table.Th>
                            <Table.Th>Last seen</Table.Th>
                        </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                        {overview.nodes.map((node) => (
                            <Table.Tr key={node.name}>
                                <Table.Td>
                                    {node.name}
                                    {node.name === overview.node && (
                                        <Badge ml="xs" size="xs">
                                            this node
                                        </Badge>
                                    )}
                                </Table.Td>
                                <Table.Td>
                                    <Group gap={4}>
                                        {node.roles?.map((role) => (
                                            <Badge
                                                key={role}
                                                size="sm"
                                                variant="light"
                                            >
                                                {role}
                                            </Badge>
                                        ))}
                                    </Group>
                                </Table.Td>
                                <Table.Td>
                                    <Badge
                                        color={
                                            node.alive
                                                ? "green"
                                                : node.seen
                                                  ? "red"
                                                  : "gray"
                                        }
                                    >
                                        {node.alive
                                            ? "online"
                                            : node.seen
                                              ? "lost"
                                              : "never seen"}
                                    </Badge>
                                </Table.Td>
                                <Table.Td>{node.address || "-"}</Table.Td>
                                <Table.Td>
                                    {node.network_state ? (
                                        <Badge
                                            variant="light"
                                            color={
                                                node.network_state ===
                                                overview.network_state
                                                    ? NETWORK_COLORS[
                                                          node.network_state
                                                      ] ?? "gray"
                                                    : "orange"
                                            }
                                        >
                                            {node.network_state}
                                        </Badge>
                                    ) : (
                                        "-"
                                    )}
                                </Table.Td>
                                <Table.Td>
                                    {node.banned_teams?.length
                                        ? node.banned_teams.join(", ")
                                        : "-"}
                                </Table.Td>
                                <Table.Td>
                                    {node.seen
                                        ? new Date(
                                              node.last_seen,
                                          ).toLocaleTimeString()
                                        : "-"}
                                </Table.Td>
                            </Table.Tr>
                        ))}
                    </Table.Tbody>
                </Table>
            </Card>
        </Stack>
    );
};
