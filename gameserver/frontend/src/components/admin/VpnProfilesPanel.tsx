import {
    ActionIcon,
    Badge,
    Card,
    Code,
    Group,
    Progress,
    Switch,
    Table,
    Text,
    Title,
    Tooltip,
} from "@mantine/core";
import { useMemo, useState } from "react";
import { FaChevronDown, FaChevronRight } from "react-icons/fa6";
import {
    PeerProfile,
    formatBytes,
    suspendProfile,
    useAdminMutation,
    usePeerTraffic,
} from "../../scripts/admin";
import { useStatusQuery } from "../../scripts/query";

/** How long ago a profile last spoke to the router, in words. */
const sinceHandshake = (handshake: number) => {
    if (!handshake) return "never";
    const seconds = Math.max(0, Math.floor(Date.now() / 1000) - handshake);
    if (seconds < 90) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
};

// A profile that handshook in the last three minutes is somebody sitting at a
// laptop right now; WireGuard rehandshakes about every two.
const ONLINE_WINDOW = 180;
const isOnline = (handshake: number) =>
    handshake > 0 && Date.now() / 1000 - handshake < ONLINE_WINDOW;

const ProfileRow = ({
    profile,
    suspended,
    onToggle,
    pending,
}: {
    profile: PeerProfile;
    suspended: boolean;
    onToggle: (suspended: boolean) => void;
    pending: boolean;
}) => (
    <Table.Tr>
        <Table.Td pl="xl">
            <Group gap="xs" wrap="nowrap">
                <Code>{profile.address}</Code>
                <Badge size="xs" variant="light" color="gray">
                    #{profile.profile}
                </Badge>
            </Group>
        </Table.Td>
        <Table.Td>{formatBytes(profile.rx + profile.tx)}</Table.Td>
        <Table.Td>
            <Text size="xs" c="dimmed">
                ↓ {formatBytes(profile.rx)} · ↑ {formatBytes(profile.tx)}
            </Text>
        </Table.Td>
        <Table.Td>
            <Group gap="xs" wrap="nowrap">
                <Badge
                    size="xs"
                    variant="light"
                    color={isOnline(profile.handshake) ? "green" : "gray"}
                >
                    {isOnline(profile.handshake) ? "online" : "idle"}
                </Badge>
                <Text size="xs" c="dimmed">
                    {sinceHandshake(profile.handshake)}
                </Text>
            </Group>
        </Table.Td>
        <Table.Td>
            <Text size="xs" c="dimmed">
                {profile.node}
            </Text>
        </Table.Td>
        <Table.Td>
            <Tooltip
                label={
                    suspended
                        ? "Let this profile back on the game network"
                        : "Cut this profile off, leaving the rest of the team alone"
                }
            >
                <Switch
                    size="xs"
                    color="red"
                    checked={suspended}
                    disabled={pending}
                    onChange={(event) => onToggle(event.currentTarget.checked)}
                    label={suspended ? "suspended" : "active"}
                />
            </Tooltip>
        </Table.Td>
    </Table.Tr>
);

export const VpnProfilesPanel = ({ minutes }: { minutes: number }) => {
    const peers = usePeerTraffic(minutes);
    const status = useStatusQuery();
    const [open, setOpen] = useState<Record<number, boolean>>({});
    const [pending, setPending] = useState<string | null>(null);

    const toggle = useAdminMutation(
        ({ address, suspended }: { address: string; suspended: boolean }) =>
            suspendProfile(address, suspended),
        ["admin"],
    );

    const teamName = useMemo(() => {
        const map = new Map<number, string>();
        for (const team of status.data?.teams ?? []) map.set(team.id, team.name);
        return (id: number) =>
            id < 0 ? "Organizers" : map.get(id) ?? `Team ${id}`;
    }, [status.data]);

    const suspended = useMemo(
        () => new Set(peers.data?.suspended ?? []),
        [peers.data],
    );

    const byTeam = useMemo(() => {
        const groups = new Map<number, PeerProfile[]>();
        for (const profile of peers.data?.profiles ?? []) {
            const list = groups.get(profile.team_id) ?? [];
            list.push(profile);
            groups.set(profile.team_id, list);
        }
        return groups;
    }, [peers.data]);

    const teams = [...(peers.data?.teams ?? [])].sort(
        (a, b) => b.rx + b.tx - (a.rx + a.tx),
    );
    const peak = teams.reduce((acc, team) => Math.max(acc, team.rx + team.tx), 0);

    return (
        <Card withBorder padding="md">
            <Title order={4}>VPN profiles</Title>
            <Text size="sm" c="dimmed">
                Counted by WireGuard itself, per peer, over the last{" "}
                {peers.data?.minutes ?? minutes} minutes: one peer is one
                profile, so this says which laptop inside a team is doing the
                talking. Suspending one takes that profile off the game network
                and leaves the rest of the team playing — a network ban takes
                the whole team out.
            </Text>

            <Table.ScrollContainer minWidth={900}>
                <Table highlightOnHover mt="sm" verticalSpacing="xs">
                    <Table.Thead>
                        <Table.Tr>
                            <Table.Th>Team / profile</Table.Th>
                            <Table.Th>Total</Table.Th>
                            <Table.Th>In / out</Table.Th>
                            <Table.Th>Last seen</Table.Th>
                            <Table.Th>Node</Table.Th>
                            <Table.Th>State</Table.Th>
                        </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                        {teams.map((team) => {
                            const profiles = byTeam.get(team.team_id) ?? [];
                            const expanded = open[team.team_id] ?? false;
                            return [
                                <Table.Tr key={`team-${team.team_id}`}>
                                    <Table.Td>
                                        <Group gap="xs" wrap="nowrap">
                                            <ActionIcon
                                                size="sm"
                                                variant="subtle"
                                                onClick={() =>
                                                    setOpen((current) => ({
                                                        ...current,
                                                        [team.team_id]:
                                                            !expanded,
                                                    }))
                                                }
                                            >
                                                {expanded ? (
                                                    <FaChevronDown size={11} />
                                                ) : (
                                                    <FaChevronRight size={11} />
                                                )}
                                            </ActionIcon>
                                            <Text fw={600}>
                                                {teamName(team.team_id)}
                                            </Text>
                                            <Badge
                                                size="xs"
                                                variant="light"
                                                color={
                                                    team.team_id < 0
                                                        ? "grape"
                                                        : "cyan"
                                                }
                                            >
                                                {team.active}/{team.profiles}{" "}
                                                online
                                            </Badge>
                                        </Group>
                                    </Table.Td>
                                    <Table.Td>
                                        <Text fw={600}>
                                            {formatBytes(team.rx + team.tx)}
                                        </Text>
                                        <Progress
                                            mt={4}
                                            size="xs"
                                            value={
                                                peak
                                                    ? ((team.rx + team.tx) /
                                                          peak) *
                                                      100
                                                    : 0
                                            }
                                            color={
                                                team.team_id < 0
                                                    ? "grape"
                                                    : "cyan"
                                            }
                                        />
                                    </Table.Td>
                                    <Table.Td>
                                        <Text size="xs" c="dimmed">
                                            ↓ {formatBytes(team.rx)} · ↑{" "}
                                            {formatBytes(team.tx)}
                                        </Text>
                                    </Table.Td>
                                    <Table.Td colSpan={3} />
                                </Table.Tr>,
                                ...(expanded
                                    ? profiles.map((profile) => (
                                          <ProfileRow
                                              key={profile.address}
                                              profile={profile}
                                              suspended={suspended.has(
                                                  profile.address,
                                              )}
                                              pending={
                                                  pending === profile.address
                                              }
                                              onToggle={(value) => {
                                                  setPending(profile.address);
                                                  toggle.mutate(
                                                      {
                                                          address:
                                                              profile.address,
                                                          suspended: value,
                                                      },
                                                      {
                                                          onSettled: () =>
                                                              setPending(null),
                                                      },
                                                  );
                                              }}
                                          />
                                      ))
                                    : []),
                            ];
                        })}
                        {teams.length === 0 && (
                            <Table.Tr>
                                <Table.Td colSpan={6}>
                                    <Text c="dimmed">
                                        No profile has moved a byte yet.
                                    </Text>
                                </Table.Td>
                            </Table.Tr>
                        )}
                    </Table.Tbody>
                </Table>
            </Table.ScrollContainer>

            {toggle.isError && (
                <Text size="sm" c="orange" mt="xs">
                    {(toggle.error as Error)?.message}
                </Text>
            )}
            {suspended.size > 0 && (
                <Text size="xs" c="dimmed" mt="xs">
                    Suspended right now:{" "}
                    {[...suspended].sort().map((address) => (
                        <Code key={address} mr={4}>
                            {address}
                        </Code>
                    ))}
                </Text>
            )}
        </Card>
    );
};
