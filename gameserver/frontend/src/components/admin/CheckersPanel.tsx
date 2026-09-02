import {
    Badge,
    Card,
    Code,
    Group,
    Select,
    Stack,
    Table,
    Text,
    TextInput,
    Title,
} from "@mantine/core";
import { useState } from "react";
import {
    AdminOverview,
    useAdminJobs,
    useAdminServices,
} from "../../scripts/admin";

const STATUS_LABELS: Record<number, { label: string; color: string }> = {
    101: { label: "OK", color: "green" },
    100: { label: "NOT CHECKED", color: "gray" },
    104: { label: "DOWN", color: "red" },
    110: { label: "ERROR", color: "grape" },
    [-1]: { label: "TIMEOUT", color: "orange" },
    1337: { label: "CRITICAL", color: "red" },
    0: { label: "-", color: "gray" },
};

export const CheckersPanel = ({ overview }: { overview: AdminOverview }) => {
    const services = useAdminServices();
    const [round, setRound] = useState("");
    const [service, setService] = useState<string | null>("");
    const [state, setState] = useState<string | null>("");
    const jobs = useAdminJobs({
        round,
        service: service ?? "",
        state: state ?? "",
    });

    return (
        <Stack gap="lg">
            <Card withBorder padding="md">
                <Title order={4}>Checker workers</Title>
                <Text size="sm" c="dimmed">
                    Workers pull jobs when they have free slots, so the load
                    balances itself: a slower machine simply claims less work.
                </Text>
                <Table striped highlightOnHover mt="sm">
                    <Table.Thead>
                        <Table.Tr>
                            <Table.Th>Worker</Table.Th>
                            <Table.Th>Address</Table.Th>
                            <Table.Th>Slots</Table.Th>
                            <Table.Th>Running</Table.Th>
                            <Table.Th>Completed</Table.Th>
                            <Table.Th>Failed</Table.Th>
                            <Table.Th>State</Table.Th>
                        </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                        {overview.workers.map((worker) => (
                            <Table.Tr key={worker.id}>
                                <Table.Td>
                                    {worker.name}
                                    {worker.embedded && (
                                        <Badge ml="xs" size="xs" variant="light">
                                            embedded
                                        </Badge>
                                    )}
                                </Table.Td>
                                <Table.Td>
                                    <Code>{worker.address || "-"}</Code>
                                </Table.Td>
                                <Table.Td>{worker.capacity}</Table.Td>
                                <Table.Td>{worker.running}</Table.Td>
                                <Table.Td>{worker.completed}</Table.Td>
                                <Table.Td>{worker.failed}</Table.Td>
                                <Table.Td>
                                    <Badge
                                        color={worker.alive ? "green" : "red"}
                                    >
                                        {worker.alive ? "alive" : "lost"}
                                    </Badge>
                                </Table.Td>
                            </Table.Tr>
                        ))}
                        {overview.workers.length === 0 && (
                            <Table.Tr>
                                <Table.Td colSpan={7}>
                                    <Text c="dimmed">
                                        No worker registered: the game cannot be
                                        checked.
                                    </Text>
                                </Table.Td>
                            </Table.Tr>
                        )}
                    </Table.Tbody>
                </Table>
            </Card>

            <Card withBorder padding="md">
                <Group align="end">
                    <Title order={4}>Checker jobs</Title>
                    <TextInput
                        label="Round"
                        placeholder={String(overview.round)}
                        value={round}
                        onChange={(event) => setRound(event.currentTarget.value)}
                        w={110}
                    />
                    <Select
                        label="Service"
                        data={[
                            { value: "", label: "All" },
                            ...(services.data ?? []).map((svc) => ({
                                value: svc.name,
                                label: svc.name,
                            })),
                        ]}
                        value={service}
                        onChange={setService}
                        w={200}
                    />
                    <Select
                        label="State"
                        data={[
                            { value: "", label: "All" },
                            { value: "queued", label: "queued" },
                            { value: "running", label: "running" },
                            { value: "done", label: "done" },
                            { value: "lost", label: "lost" },
                        ]}
                        value={state}
                        onChange={setState}
                        w={150}
                    />
                </Group>
                <Table.ScrollContainer minWidth={900}>
                    <Table striped highlightOnHover mt="sm" verticalSpacing="xs">
                        <Table.Thead>
                            <Table.Tr>
                                <Table.Th>Round</Table.Th>
                                <Table.Th>Team</Table.Th>
                                <Table.Th>Service</Table.Th>
                                <Table.Th>Action</Table.Th>
                                <Table.Th>State</Table.Th>
                                <Table.Th>Status</Table.Th>
                                <Table.Th>Worker</Table.Th>
                                <Table.Th>Time</Table.Th>
                                <Table.Th>Message</Table.Th>
                            </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                            {(jobs.data ?? []).map((job) => {
                                const status =
                                    STATUS_LABELS[job.status] ??
                                    STATUS_LABELS[0];
                                return (
                                    <Table.Tr key={job.id}>
                                        <Table.Td>{job.round}</Table.Td>
                                        <Table.Td>{job.team_id}</Table.Td>
                                        <Table.Td>{job.service}</Table.Td>
                                        <Table.Td>{job.action}</Table.Td>
                                        <Table.Td>{job.state}</Table.Td>
                                        <Table.Td>
                                            <Badge
                                                size="sm"
                                                color={status.color}
                                            >
                                                {status.label}
                                            </Badge>
                                        </Table.Td>
                                        <Table.Td>{job.worker || "-"}</Table.Td>
                                        <Table.Td>
                                            {job.duration_ms
                                                ? `${(job.duration_ms / 1000).toFixed(1)}s`
                                                : "-"}
                                        </Table.Td>
                                        <Table.Td>
                                            <Text size="xs" lineClamp={2}>
                                                {job.message}
                                            </Text>
                                        </Table.Td>
                                    </Table.Tr>
                                );
                            })}
                        </Table.Tbody>
                    </Table>
                </Table.ScrollContainer>
            </Card>
        </Stack>
    );
};
