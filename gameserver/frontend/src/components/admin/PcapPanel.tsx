import {
    Alert,
    Badge,
    Button,
    Card,
    Code,
    Group,
    MultiSelect,
    NumberInput,
    SegmentedControl,
    Stack,
    Table,
    Text,
    TextInput,
    Title,
} from "@mantine/core";
import { useState } from "react";
import { FaDownload } from "react-icons/fa6";
import { formatBytes, pcapDownloadUrl, usePcapStatus } from "../../scripts/admin";
import { useStatusQuery } from "../../scripts/query";

type RangeMode = "all" | "rounds" | "minutes" | "interval";

const RANGES = [
    { value: "minutes", label: "Last minutes" },
    { value: "rounds", label: "Rounds" },
    { value: "interval", label: "Interval" },
    { value: "all", label: "Everything" },
];

const stamp = (seconds: number | null) =>
    seconds ? new Date(seconds * 1000).toLocaleString() : "-";

export const PcapPanel = () => {
    const pcap = usePcapStatus();
    const status = useStatusQuery();
    const [mode, setMode] = useState<RangeMode>("minutes");
    const [teams, setTeams] = useState<string[]>([]);
    const [minutes, setMinutes] = useState<number | string>(10);
    const [fromRound, setFromRound] = useState<number | string>("");
    const [toRound, setToRound] = useState<number | string>("");
    const [from, setFrom] = useState("");
    const [to, setTo] = useState("");
    const [filter, setFilter] = useState("");

    const nodes = pcap.data?.nodes ?? [];
    const enabled = pcap.data?.enabled ?? false;

    const download = () => {
        const params: Record<string, string> = {};
        if (teams.length > 0) params.teams = teams.join(",");
        if (filter.trim()) params.filter = filter.trim();
        if (mode === "minutes" && minutes) params.minutes = String(minutes);
        if (mode === "rounds") {
            if (fromRound !== "") params.from_round = String(fromRound);
            if (toRound !== "") params.to_round = String(toRound);
        }
        if (mode === "interval") {
            if (from) params.from = new Date(from).toISOString();
            if (to) params.to = new Date(to).toISOString();
        }
        window.location.href = pcapDownloadUrl(params);
    };

    return (
        <Card withBorder padding="md">
            <Group justify="space-between">
                <Title order={4}>Packet capture</Title>
                <Badge color={enabled ? "green" : "gray"} variant="light">
                    {enabled ? "recording" : "off"}
                </Badge>
            </Group>
            <Text size="sm" c="dimmed">
                The routers keep a rotating capture of the game interface and
                serve slices of it on demand. Nothing is stored on the control
                node: the download is streamed straight from the routers.
            </Text>

            {!enabled && (
                <Alert color="gray" mt="sm" variant="light">
                    Capture is off. Set <Code>"pcap": true</Code> in
                    config.json (and optionally{" "}
                    <Code>"pcap_max_size"</Code>, the ring size in MB per
                    router) and restart the routers.
                </Alert>
            )}

            <Table mt="sm" verticalSpacing="xs">
                <Table.Thead>
                    <Table.Tr>
                        <Table.Th>Node</Table.Th>
                        <Table.Th>Interface</Table.Th>
                        <Table.Th>Files</Table.Th>
                        <Table.Th>On disk</Table.Th>
                        <Table.Th>Oldest packet</Table.Th>
                        <Table.Th>Newest packet</Table.Th>
                    </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                    {nodes.map((node) => (
                        <Table.Tr key={node.node}>
                            <Table.Td>{node.node}</Table.Td>
                            <Table.Td>
                                <Code>{node.interface || "-"}</Code>
                            </Table.Td>
                            <Table.Td>{node.files}</Table.Td>
                            <Table.Td>
                                {formatBytes(node.bytes)}
                                {node.max_bytes > 0 && (
                                    <Text span c="dimmed" size="xs">
                                        {" "}
                                        / {formatBytes(node.max_bytes)}
                                    </Text>
                                )}
                            </Table.Td>
                            <Table.Td>{stamp(node.oldest)}</Table.Td>
                            <Table.Td>{stamp(node.newest)}</Table.Td>
                        </Table.Tr>
                    ))}
                    {nodes.some((node) => node.error) && (
                        <Table.Tr>
                            <Table.Td colSpan={6}>
                                <Text c="orange" size="sm">
                                    {nodes
                                        .filter((node) => node.error)
                                        .map(
                                            (node) =>
                                                `${node.node}: ${node.error}`,
                                        )
                                        .join(" · ")}
                                </Text>
                            </Table.Td>
                        </Table.Tr>
                    )}
                    {nodes.length === 0 && (
                        <Table.Tr>
                            <Table.Td colSpan={6}>
                                <Text c="dimmed">No router answered.</Text>
                            </Table.Td>
                        </Table.Tr>
                    )}
                </Table.Tbody>
            </Table>

            <Stack gap="sm" mt="md">
                <Group>
                    <SegmentedControl
                        size="xs"
                        data={RANGES}
                        value={mode}
                        onChange={(value) => setMode(value as RangeMode)}
                    />
                    {mode === "minutes" && (
                        <NumberInput
                            size="xs"
                            w={140}
                            min={1}
                            max={1440}
                            label="Minutes"
                            value={minutes}
                            onChange={setMinutes}
                        />
                    )}
                    {mode === "rounds" && (
                        <>
                            <NumberInput
                                size="xs"
                                w={120}
                                min={0}
                                label="From round"
                                value={fromRound}
                                onChange={setFromRound}
                            />
                            <NumberInput
                                size="xs"
                                w={120}
                                min={0}
                                label="To round"
                                value={toRound}
                                onChange={setToRound}
                            />
                        </>
                    )}
                    {mode === "interval" && (
                        <>
                            <TextInput
                                size="xs"
                                type="datetime-local"
                                label="From"
                                value={from}
                                onChange={(e) => setFrom(e.currentTarget.value)}
                            />
                            <TextInput
                                size="xs"
                                type="datetime-local"
                                label="To"
                                value={to}
                                onChange={(e) => setTo(e.currentTarget.value)}
                            />
                        </>
                    )}
                </Group>
                <Group align="end">
                    <MultiSelect
                        size="xs"
                        w={320}
                        label="Teams"
                        placeholder={teams.length ? "" : "every team"}
                        searchable
                        clearable
                        value={teams}
                        onChange={setTeams}
                        data={(status.data?.teams ?? []).map((team) => ({
                            value: String(team.id),
                            label: `${team.id} — ${team.name}`,
                        }))}
                    />
                    <TextInput
                        size="xs"
                        flex={1}
                        label="Extra BPF filter"
                        placeholder="tcp port 8000"
                        value={filter}
                        onChange={(e) => setFilter(e.currentTarget.value)}
                    />
                    <Button
                        size="xs"
                        leftSection={<FaDownload />}
                        onClick={download}
                        disabled={!enabled}
                    >
                        Download
                    </Button>
                </Group>
                <Text size="xs" c="dimmed">
                    Always one <Code>.pcap</Code>: the routers of a distributed
                    deployment are merged in timestamp order on the way out.
                    Team filtering keeps every packet with that team on either
                    side, vulnbox and player tunnel alike. A wide range takes a
                    while — the file is streamed as it is read, so the download
                    starts long before the routers are done.
                </Text>
            </Stack>
        </Card>
    );
};
