import { Alert, Badge, Group, Stack, Text } from "@mantine/core";
import { MdAcUnit, MdCampaign, MdPause } from "react-icons/md";
import { FaLock, FaSnowflake } from "react-icons/fa6";
import { useAnnouncementsQuery, useStatusQuery } from "../scripts/query";

/**
 * What each network state means to a player. `unlocked` is the normal state of
 * a running game and says nothing worth interrupting anybody for; every other
 * state explains why the vulnboxes are not answering.
 */
const NETWORK_STATES: Record<
    string,
    { title: string; color: string; body: string; icon: React.ReactNode }
> = {
    frozen: {
        title: "Network frozen",
        color: "red",
        icon: <FaSnowflake size={18} />,
        body: "The game network is closed: you can reach the scoreboard and the game server, but no vulnbox yet, not even your own.",
    },
    locked: {
        title: "Network locked",
        color: "yellow",
        icon: <FaLock size={16} />,
        body: "You can reach your own vulnbox to prepare and patch it, but not the other teams. Attacks open when the game starts.",
    },
};

const SEVERITY_COLORS: Record<string, string> = {
    info: "blue",
    warning: "yellow",
    critical: "red",
};

/** Everything the players must know at a glance: freeze, pause and the
 * organizers' announcements. */
export const GameBanners = () => {
    const status = useStatusQuery();
    const announcements = useAnnouncementsQuery();

    const frozen = status.data?.scoreboard_frozen;
    const paused = status.data?.game_paused;
    const items = announcements.data ?? [];
    const network = NETWORK_STATES[status.data?.network_state ?? ""];

    if (!frozen && !paused && !network && items.length === 0) return null;

    return (
        <Stack gap="sm" mb="lg">
            {network && (
                <Alert
                    color={network.color}
                    icon={network.icon}
                    title={network.title}
                >
                    {network.body}
                </Alert>
            )}
            {paused && (
                <Alert
                    color="orange"
                    icon={<MdPause size={20} />}
                    title="Game paused"
                >
                    The organizers paused the competition: checks are stopped and
                    flag submission is closed.
                </Alert>
            )}
            {frozen && (
                <Alert
                    color="blue"
                    icon={<MdAcUnit size={20} />}
                    title="Scoreboard frozen"
                >
                    The ranking is frozen at round{" "}
                    {status.data?.freeze_round ?? "?"}. Service status and SLA
                    keep updating, the points do not: the final standings will be
                    revealed at the end.
                </Alert>
            )}
            {items.slice(0, 3).map((item) => (
                <Alert
                    key={item.id}
                    color={SEVERITY_COLORS[item.severity] ?? "blue"}
                    icon={<MdCampaign size={20} />}
                    title={
                        <Group gap="xs">
                            <span>{item.title}</span>
                            <Badge size="xs" variant="light">
                                {new Date(item.at).toLocaleTimeString()}
                            </Badge>
                        </Group>
                    }
                >
                    <Text size="sm">{item.body}</Text>
                </Alert>
            ))}
        </Stack>
    );
};
