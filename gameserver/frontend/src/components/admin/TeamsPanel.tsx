import {
    ActionIcon,
    Badge,
    Button,
    Card,
    Code,
    Group,
    Stack,
    Switch,
    Table,
    Text,
    TextInput,
    Title,
    Tooltip,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import { useState } from "react";
import { FaEye, FaEyeSlash } from "react-icons/fa6";
import { MdRefresh, MdRestartAlt } from "react-icons/md";
import {
    AdminTeam,
    adminSend,
    useAdminMutation,
    useAdminTeams,
} from "../../scripts/admin";

const patchTeam = (id: number, body: object) =>
    adminSend(`/teams/${id}`, "PATCH", body);

const resetVM = (id: number) => adminSend(`/teams/${id}/reset-vm`, "POST");

const TeamRow = ({ team }: { team: AdminTeam }) => {
    const [name, setName] = useState(team.name);
    const [image, setImage] = useState(team.image);
    const [reason, setReason] = useState(team.ban_reason);
    const [showToken, setShowToken] = useState(false);

    const mutate = useAdminMutation((body: object) => patchTeam(team.id, body));
    const reset = useAdminMutation(() => resetVM(team.id));
    const dirty = name !== team.name || image !== team.image;

    // A reset throws away everything the team built on its box, so it asks
    // once, by name, before it happens.
    const confirmReset = () =>
        modals.openConfirmModal({
            title: `Reset the box of ${team.name}?`,
            centered: true,
            children: (
                <Text size="sm">
                    The box goes back to the state it started the game in.
                    Every patch, tool and exploit the team put on it is lost,
                    and the box is unreachable while it rebuilds — a few
                    minutes. The score and the SLA are not touched.
                </Text>
            ),
            labels: { confirm: "Reset the box", cancel: "Cancel" },
            confirmProps: { color: "red" },
            onConfirm: () => reset.mutate(undefined as never),
        });

    return (
        <Table.Tr>
            <Table.Td>{team.id}</Table.Td>
            <Table.Td>
                <TextInput
                    value={name}
                    onChange={(event) => setName(event.currentTarget.value)}
                    w={200}
                />
            </Table.Td>
            <Table.Td>
                <TextInput
                    value={image}
                    placeholder="logo.png or https://..."
                    onChange={(event) => setImage(event.currentTarget.value)}
                    w={200}
                />
            </Table.Td>
            <Table.Td>
                <Code>{team.ip}</Code>
                {team.nop && (
                    <Badge ml="xs" size="xs" color="gray">
                        nop
                    </Badge>
                )}
            </Table.Td>
            <Table.Td>
                <Group gap={4} wrap="nowrap">
                    <Code style={{ maxWidth: 160, overflow: "hidden" }}>
                        {showToken ? team.token : "•".repeat(16)}
                    </Code>
                    <ActionIcon
                        variant="subtle"
                        onClick={() => setShowToken((value) => !value)}
                    >
                        {showToken ? <FaEyeSlash /> : <FaEye />}
                    </ActionIcon>
                    <Tooltip label="Rotate the submission token">
                        <ActionIcon
                            variant="subtle"
                            color="orange"
                            loading={mutate.isPending}
                            onClick={() => mutate.mutate({ rotate_token: true })}
                        >
                            <MdRefresh />
                        </ActionIcon>
                    </Tooltip>
                </Group>
            </Table.Td>
            <Table.Td>
                <Stack gap={4}>
                    <Switch
                        size="xs"
                        label="Submission ban"
                        checked={team.game_banned}
                        onChange={(event) =>
                            mutate.mutate({
                                game_banned: event.currentTarget.checked,
                                ban_reason: reason,
                            })
                        }
                    />
                    <Switch
                        size="xs"
                        color="red"
                        label="Network ban"
                        checked={team.network_banned}
                        onChange={(event) =>
                            mutate.mutate({
                                network_banned: event.currentTarget.checked,
                                ban_reason: reason,
                            })
                        }
                    />
                </Stack>
            </Table.Td>
            <Table.Td>
                <TextInput
                    size="xs"
                    placeholder="Ban reason"
                    value={reason}
                    onChange={(event) => setReason(event.currentTarget.value)}
                    onBlur={() => {
                        if (reason !== team.ban_reason)
                            mutate.mutate({ ban_reason: reason });
                    }}
                    w={180}
                />
            </Table.Td>
            <Table.Td>
                <Group gap={4} wrap="nowrap">
                    <Button
                        size="xs"
                        disabled={!dirty}
                        loading={mutate.isPending}
                        onClick={() => mutate.mutate({ name, image })}
                    >
                        Save
                    </Button>
                    <Tooltip label="Reset the box to its original state">
                        <ActionIcon
                            variant="subtle"
                            color="red"
                            loading={reset.isPending}
                            onClick={confirmReset}
                        >
                            <MdRestartAlt />
                        </ActionIcon>
                    </Tooltip>
                </Group>
                {reset.isError && (
                    <Text size="xs" c="orange" mt={4} maw={260}>
                        {(reset.error as Error).message}
                    </Text>
                )}
                {reset.isSuccess && (
                    <Text size="xs" c="teal" mt={4}>
                        Rebuilding, it takes a few minutes.
                    </Text>
                )}
            </Table.Td>
        </Table.Tr>
    );
};

export const TeamsPanel = () => {
    const teams = useAdminTeams();

    if (teams.isLoading) return <Text>Loading teams...</Text>;
    if (teams.isError)
        return <Text c="red">{(teams.error as Error).message}</Text>;

    return (
        <Card withBorder padding="md">
            <Title order={4}>Teams</Title>
            <Text size="sm" c="dimmed">
                A submission ban stops the team from scoring; a network ban cuts
                its players off the game network on every router. Resetting a
                box rebuilds it from the original image, which only works for
                boxes hosted on this machine — elsewhere, run
                <Code>./run.py resetvm &lt;team&gt;</Code> from where you deploy.
            </Text>
            <Table.ScrollContainer minWidth={1100}>
                <Table striped highlightOnHover mt="sm" verticalSpacing="xs">
                    <Table.Thead>
                        <Table.Tr>
                            <Table.Th>#</Table.Th>
                            <Table.Th>Name</Table.Th>
                            <Table.Th>Image</Table.Th>
                            <Table.Th>Host</Table.Th>
                            <Table.Th>Token</Table.Th>
                            <Table.Th>Bans</Table.Th>
                            <Table.Th>Reason</Table.Th>
                            <Table.Th />
                        </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                        {(teams.data ?? []).map((team) => (
                            <TeamRow key={team.id} team={team} />
                        ))}
                    </Table.Tbody>
                </Table>
            </Table.ScrollContainer>
        </Card>
    );
};
