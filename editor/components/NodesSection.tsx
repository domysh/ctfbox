"use client";

import {
    ActionIcon,
    Alert,
    Badge,
    Button,
    Card,
    Code,
    Group,
    List,
    MultiSelect,
    SimpleGrid,
    Space,
    Stack,
    Switch,
    Table,
    Text,
    TextInput,
    Tooltip,
} from "@mantine/core";
import { NumberField } from "./NumberField";
import { MdAdd, MdDelete, MdWarningAmber } from "react-icons/md";
import { FaSitemap } from "react-icons/fa6";
import {
    ALL_ROLES,
    Config,
    Node,
    defaultNode,
    rolesPatch,
} from "@/lib/config";
import { topologySummary, validateTopology } from "@/lib/topology";
import { SectionCard } from "./SectionCard";

const parseIds = (value: string): number[] =>
    value
        .split(/[\s,]+/)
        .map((part) => Number.parseInt(part, 10))
        .filter((id) => Number.isInteger(id) && id >= 0);

const formatIds = (ids: number[]): string => ids.join(", ");

/** What an operator has to have ready before `./run.py deploy` works. */
const DeployGuide = () => (
    <Card withBorder radius="md" padding="md">
        <Group mb={6}>
            <FaSitemap size={14} />
            <Text fw={600}>Before you deploy</Text>
        </Group>
        <List spacing={6} size="sm" c="dimmed">
            <List.Item>
                <b>Docker on every machine.</b> That is the only thing the
                other nodes need installed: the deploy carries everything else
                in containers, rsync included, and stops with a clear message if{" "}
                <Code>docker version</Code> does not answer.
            </List.Item>
            <List.Item>
                <b>Key based ssh from the machine you deploy from.</b> Run{" "}
                <Code>ssh-keygen -t ed25519</Code> once, then{" "}
                <Code>ssh-copy-id user@node</Code> for each node, and check that{" "}
                <Code>ssh user@node docker version</Code> works without a
                password. If the user is not root, add it to the{" "}
                <Code>docker</Code> group. That machine needs{" "}
                <Code>ssh</Code> and <Code>rsync</Code>.
            </List.Item>
            <List.Item>
                <b>Two addresses per node.</b> The internal one is how the nodes
                reach each other — the mesh, the deploy and the internal APIs
                all prefer it, so a private network between the machines is
                ideal. The public one is how players reach it and has to resolve
                from the internet; only VPN nodes need it.
            </List.Item>
            <List.Item>
                <b>Ports.</b> Each VPN node publishes its WireGuard port, and
                one more just above it for the node to node mesh. Nothing else
                has to be open: the nodes talk to the game server through the
                tunnels.
            </List.Item>
        </List>
        <Space h="sm" />
        <Text size="sm" c="dimmed">
            Then, from the control node:
        </Text>
        <Code block mt={6}>
            {`./run.py node list    # check the topology and the team assignment
./run.py deploy       # control node first, then every node over ssh`}
        </Code>
        <Text size="xs" c="dimmed" mt={6}>
            A node with no ssh target is skipped, to be started by hand with{" "}
            <Code>./run.py node up &lt;name&gt;</Code> on that machine.
        </Text>
    </Card>
);

const NodeCard = ({
    node,
    index,
    onChange,
    onRemove,
}: {
    node: Node;
    index: number;
    onChange: (patch: Partial<Node>) => void;
    onRemove: () => void;
}) => {
    const isVpn = node.roles.includes("vpn") || node.roles.includes("router");
    // Exactly one node owns the game server and the database, and a deployment
    // without it is not a deployment. The first node is that node: it keeps the
    // control role and cannot be removed. Its name is yours to choose like any
    // other.
    const isControl = index === 0;

    return (
        <Card withBorder radius="md" padding="md">
            <Group mb="sm" wrap="nowrap">
                <Badge variant="light">#{index + 1}</Badge>
                <Text fw={600}>{node.name || "unnamed"}</Text>
                {isControl && (
                    <Badge variant="light" color="grape">
                        control
                    </Badge>
                )}
                <div style={{ flex: 1 }} />
                <Tooltip
                    label={
                        isControl
                            ? "The control node cannot be removed"
                            : "Remove this node"
                    }
                >
                    <ActionIcon
                        color="red"
                        variant="subtle"
                        onClick={onRemove}
                        disabled={isControl}
                        aria-label="Remove node"
                    >
                        <MdDelete />
                    </ActionIcon>
                </Tooltip>
            </Group>

            <SimpleGrid cols={{ base: 1, md: 2, lg: 3 }} spacing="sm">
                <TextInput
                    label="Name"
                    description="Used by ./run.py node <action> <name>"
                    value={node.name}
                    onChange={(event) =>
                        onChange({ name: event.currentTarget.value })
                    }
                />
                <MultiSelect
                    label="Roles"
                    description={
                        isControl
                            ? "The control role stays here; add what else it does"
                            : "What this machine takes care of"
                    }
                    data={ALL_ROLES.map((role) => ({
                        value: role,
                        label: role,
                        // Only the first node runs the game server, so the role
                        // is neither removable here nor available elsewhere.
                        disabled: role === "control",
                    }))}
                    value={node.roles.filter((role) =>
                        (ALL_ROLES as readonly string[]).includes(role),
                    )}
                    onChange={(roles) =>
                        onChange(
                            rolesPatch(
                                node,
                                isControl
                                    ? [
                                          "control",
                                          ...roles.filter((r) => r !== "control"),
                                      ]
                                    : roles.filter((r) => r !== "control"),
                            ),
                        )
                    }
                />
                <TextInput
                    label="Internal address"
                    description="How the other nodes reach it, ideally a private network"
                    placeholder="10.0.0.2"
                    value={node.address}
                    onChange={(event) =>
                        onChange({ address: event.currentTarget.value })
                    }
                />
                {/* Shown when it applies, and also whenever the node carries one
                    anyway (a config written elsewhere): a value that is going to
                    be exported must never be invisible here. */}
                {(isVpn || node.public_address) && (
                    <TextInput
                        label="Public address"
                        description={
                            isVpn
                                ? "How players reach it, must resolve from the internet"
                                : "Unused: this node terminates no tunnel. Clear it or give it the vpn role."
                        }
                        placeholder="node2.example.com"
                        error={!isVpn && node.public_address ? true : undefined}
                        value={node.public_address}
                        onChange={(event) =>
                            onChange({ public_address: event.currentTarget.value })
                        }
                    />
                )}
                <TextInput
                    label="SSH target"
                    description="user@host, or just the user to reuse the internal address"
                    placeholder="ctf@10.0.0.2"
                    value={node.ssh}
                    onChange={(event) =>
                        onChange({ ssh: event.currentTarget.value })
                    }
                />
                <TextInput
                    label="Remote path"
                    description="Where the sources are copied on that machine"
                    placeholder="~/ctfbox"
                    value={node.path}
                    onChange={(event) =>
                        onChange({ path: event.currentTarget.value })
                    }
                />
                <NumberField
                    label="Weight"
                    description="Share of the teams it takes"
                    min={1}
                    value={node.weight}
                    fallback={1}
                    onValueChange={(value) => onChange({ weight: value })}
                />
                {(node.roles.includes("checker") ||
                    node.checker_concurrency > 0) && (
                    <NumberField
                        label="Checker concurrency"
                        description="0 uses this node's CPUs"
                        min={0}
                        value={node.checker_concurrency}
                        fallback={0}
                        onValueChange={(value) =>
                            onChange({ checker_concurrency: value })
                        }
                    />
                )}
                <TextInput
                    label="Pinned tunnels"
                    description="Team ids, empty for automatic"
                    placeholder="auto"
                    value={formatIds(node.teams)}
                    onChange={(event) =>
                        onChange({ teams: parseIds(event.currentTarget.value) })
                    }
                />
                <TextInput
                    label="Pinned vulnboxes"
                    description="Overrides the line above for the VMs only"
                    placeholder="auto"
                    value={formatIds(node.vm_teams)}
                    onChange={(event) =>
                        onChange({ vm_teams: parseIds(event.currentTarget.value) })
                    }
                />
            </SimpleGrid>
        </Card>
    );
};

export const NodesSection = ({
    config,
    update,
}: {
    config: Config;
    update: (patch: Partial<Config>) => void;
}) => {
    const distributed = config.nodes.length > 0;
    const warnings = validateTopology(config);
    const summary = topologySummary(config);

    const setNode = (index: number, patch: Partial<Node>) =>
        update({
            nodes: config.nodes.map((node, i) =>
                i === index ? { ...node, ...patch } : node,
            ),
        });

    return (
        <SectionCard
            title="Topology"
            icon={<FaSitemap size={16} />}
            description="One machine runs everything by default. Declare nodes to spread the same game over several machines: the tunnels, the vulnboxes and the checkers are distributed independently."
            actions={
                <Switch
                    label="Distributed"
                    checked={distributed}
                    onChange={(event) =>
                        update({
                            nodes: event.currentTarget.checked
                                ? [defaultNode(0), defaultNode(1)]
                                : [],
                        })
                    }
                />
            }
        >
            {!distributed ? (
                <Alert color="gray">
                    Single machine deployment: <Code>./run.py start</Code> brings
                    up the router, the game server, the database and every
                    vulnbox on this host. Turn on “Distributed” to add nodes.
                </Alert>
            ) : (
                <Stack gap="md">
                    <DeployGuide />
                    {warnings.length > 0 && (
                        <Alert
                            color="yellow"
                            icon={<MdWarningAmber size={20} />}
                            title="Check the topology"
                        >
                            <Stack gap={4}>
                                {warnings.map((warning) => (
                                    <Text size="sm" key={warning}>
                                        {warning}
                                    </Text>
                                ))}
                            </Stack>
                        </Alert>
                    )}

                    {config.nodes.map((node, index) => (
                        <NodeCard
                            key={index}
                            node={node}
                            index={index}
                            onChange={(patch) => setNode(index, patch)}
                            onRemove={() =>
                                update({
                                    nodes: config.nodes.filter(
                                        (_, i) => i !== index,
                                    ),
                                })
                            }
                        />
                    ))}

                    <Group>
                        <Button
                            variant="light"
                            leftSection={<MdAdd />}
                            onClick={() =>
                                update({
                                    nodes: [
                                        ...config.nodes,
                                        defaultNode(config.nodes.length),
                                    ],
                                })
                            }
                        >
                            Add a node
                        </Button>
                    </Group>

                    <Card withBorder radius="md" padding="md">
                        <Text fw={600} mb={4}>
                            Planned distribution
                        </Text>
                        <Text size="sm" c="dimmed" mb="sm">
                            Exactly what <Code>./run.py node list</Code> will
                            report: a weighted round robin over the nodes of each
                            role, with the pinned teams honoured first.
                        </Text>
                        <Table striped highlightOnHover>
                            <Table.Thead>
                                <Table.Tr>
                                    <Table.Th>Node</Table.Th>
                                    <Table.Th>Roles</Table.Th>
                                    <Table.Th>Tunnels</Table.Th>
                                    <Table.Th>Vulnboxes</Table.Th>
                                </Table.Tr>
                            </Table.Thead>
                            <Table.Tbody>
                                {summary.map(({ node, vpnTeams, vmTeams }) => (
                                    <Table.Tr key={node.name}>
                                        <Table.Td>{node.name}</Table.Td>
                                        <Table.Td>
                                            <Group gap={4}>
                                                {node.roles.map((role) => (
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
                                            {vpnTeams.length
                                                ? formatIds(vpnTeams)
                                                : "-"}
                                        </Table.Td>
                                        <Table.Td>
                                            {vmTeams.length
                                                ? formatIds(vmTeams)
                                                : "-"}
                                        </Table.Td>
                                    </Table.Tr>
                                ))}
                            </Table.Tbody>
                        </Table>
                    </Card>
                </Stack>
            )}
        </SectionCard>
    );
};
