import {
    ActionIcon,
    Alert,
    Anchor,
    Badge,
    Box,
    Code,
    CopyButton,
    Flex,
    Group,
    List,
    Paper,
    SimpleGrid,
    Space,
    Text,
    ThemeIcon,
    Title,
    Tooltip,
} from "@mantine/core";
import { ReactNode, useEffect } from "react";
import { FaCheck, FaCopy, FaFlag } from "react-icons/fa6";
import { FaHandshake } from "react-icons/fa";
import { GiCrosshair } from "react-icons/gi";
import { ImTarget } from "react-icons/im";
import { IoSpeedometer } from "react-icons/io5";
import { MdOutlineTag } from "react-icons/md";
import { RiRadarLine } from "react-icons/ri";
import { TbNetwork } from "react-icons/tb";
import { useStatusQuery } from "../scripts/query";
import { secondDurationToString } from "../scripts/time";
import { useGlobalState } from "../scripts/utils";

/** One rule chapter: an anchor the table of contents can jump to, a heading
 *  that says what it is about, and the text itself. */
const Section = ({
    id,
    title,
    icon,
    children,
}: {
    id: string;
    title: string;
    icon: ReactNode;
    children: ReactNode;
}) => (
    <Paper
        id={id}
        component="section"
        withBorder
        radius="md"
        p={{ base: "md", sm: "xl" }}
        mt="lg"
        style={{ scrollMarginTop: 80 }}
    >
        <Group gap="sm" mb="md" wrap="nowrap">
            <ThemeIcon size={36} radius="md" variant="light" color="cyan">
                {icon}
            </ThemeIcon>
            <Title order={2} size="h3">
                {title}
            </Title>
        </Group>
        {children}
    </Paper>
);

/** A single number worth knowing before the game starts. */
const Stat = ({
    label,
    value,
    hint,
}: {
    label: string;
    value: ReactNode;
    hint?: string;
}) => (
    <Paper withBorder radius="md" p="md">
        <Text size="xs" tt="uppercase" c="dimmed" fw={700}>
            {label}
        </Text>
        <Text size="xl" fw={700} mt={4} style={{ lineHeight: 1.2 }}>
            {value}
        </Text>
        {hint && (
            <Text size="xs" c="dimmed" mt={4}>
                {hint}
            </Text>
        )}
    </Paper>
);

/** Code you are meant to copy, with a button that does it for you. */
const Snippet = ({ children }: { children: string }) => (
    <Box pos="relative" mt="md">
        <CopyButton value={children} timeout={1500}>
            {({ copied, copy }) => (
                <Tooltip label={copied ? "Copied" : "Copy"} withArrow>
                    <ActionIcon
                        variant="subtle"
                        color={copied ? "teal" : "gray"}
                        onClick={copy}
                        pos="absolute"
                        top={8}
                        right={8}
                        style={{ zIndex: 1 }}
                    >
                        {copied ? <FaCheck size={13} /> : <FaCopy size={13} />}
                    </ActionIcon>
                </Tooltip>
            )}
        </CopyButton>
        <Code block style={{ paddingRight: 44 }}>
            {children}
        </Code>
    </Box>
);

const CHAPTERS = [
    { id: "network", label: "Network and setup" },
    { id: "scoring", label: "Scoring" },
    { id: "checks", label: "Service checks" },
    { id: "flags", label: "Flags" },
    { id: "flagids", label: "Flag IDs" },
    { id: "fairplay", label: "Fair play" },
];

const TableOfContents = () => (
    <Box style={{ position: "sticky", top: 80 }} component="nav">
        <Text size="xs" tt="uppercase" c="dimmed" fw={700} mb="xs">
            On this page
        </Text>
        {CHAPTERS.map((chapter) => (
            <Anchor
                key={chapter.id}
                href={`#${chapter.id}`}
                display="block"
                py={6}
                size="sm"
                c="dimmed"
                underline="never"
                style={{ borderLeft: "2px solid var(--mantine-color-dark-4)", paddingLeft: 12 }}
            >
                {chapter.label}
            </Anchor>
        ))}
    </Box>
);

export const RulesContent = () => {
    const config = useStatusQuery();
    const nopTeam = config.data?.teams.find((team) => team.nop);
    const setLoading = useGlobalState((state) => state.setLoading);

    useEffect(() => {
        if (config.isFetching && !config.isSuccess) {
            setLoading(true);
        } else {
            setLoading(false);
        }
    }, [config.isFetching, setLoading]);

    if (!config.isSuccess) return null;
    const data = config.data;

    return (
        <Flex maw={1500} mx="auto" mt="md" gap="xl" align="flex-start">
            <Box flex={1} miw={0}>
                <Box component="header">
                    <Group gap="sm">
                        <Title order={1}>Rules</Title>
                        <Badge size="lg" variant="light" color="cyan">
                            Attack / Defence
                        </Badge>
                    </Group>
                    <Text mt="sm" size="lg" c="dimmed" maw={800}>
                        Welcome to CTFBox. Attack the other teams to steal their
                        flags, keep your own services alive, and submit what you
                        capture before it expires.
                    </Text>
                </Box>

                <SimpleGrid cols={{ base: 2, sm: 3, md: 5 }} spacing="md" mt="xl">
                    <Stat
                        label="Round"
                        value={secondDurationToString(data.roundTime)}
                        hint="One tick of the game"
                    />
                    <Stat
                        label="Flag lifetime"
                        value={`${data.flag_expire_ticks} rounds`}
                        hint={secondDurationToString(
                            data.roundTime * data.flag_expire_ticks,
                        )}
                    />
                    <Stat
                        label="Service start score"
                        value={data.init_service_points}
                        hint="Before any flag moves"
                    />
                    <Stat
                        label="Flags per request"
                        value={data.submitter_flags_limit}
                        hint="The rest is ignored"
                    />
                    <Stat
                        label="Submission limit"
                        value={
                            data.submitter_rate_limit
                                ? `1 / ${secondDurationToString(
                                      data.submitter_rate_limit / 1000,
                                  )}`
                                : "No limit"
                        }
                        hint={
                            data.submitter_rate_limit
                                ? "Requests per team"
                                : "Submit as often as you like"
                        }
                    />
                </SimpleGrid>

                <Alert
                    mt="xl"
                    variant="light"
                    color="cyan"
                    icon={<TbNetwork size={20} />}
                    title="Where these rules come from"
                >
                    The infrastructure follows the model of the{" "}
                    <Anchor href="https://ad.cyberchallenge.it/rules" target="_blank">
                        CyberChallenge A/D infrastructure
                    </Anchor>{" "}
                    created by the{" "}
                    <Anchor href="https://cybersecnatlab.it/" target="_blank">
                        CINI Cybersecurity National Lab
                    </Anchor>
                    : the rules and the network schema are taken from there.
                </Alert>

                <Section
                    id="network"
                    title="Network and setup"
                    icon={<TbNetwork size={20} />}
                >
                    <Text>
                        The game is played within the 10.0.0.0/8 subnet. Each
                        team has its own vulnerable machine at{" "}
                        <Code>10.60.team_id.1</Code>, while players connecting
                        to the game network are assigned an address in{" "}
                        <Code>10.80.team_id.0/24</Code>.
                    </Text>
                    {nopTeam && (
                        <Alert mt="md" variant="light" color="gray">
                            <Code>{nopTeam.host}</Code> is the NOP team
                            (non-playing) vulnerable machine. It is never
                            patched and its flags do not count towards the
                            scoreboard, so use it to test your attacks.
                        </Alert>
                    )}
                    <Box className="center-flex" mt="lg">
                        <img
                            src="/images/network-1nop.svg"
                            alt="Network diagram"
                            style={{ maxWidth: "100%", height: "auto" }}
                        />
                    </Box>
                    <Text mt="lg">
                        The Game System dispatches flags to the vulnerable
                        machines, checks the integrity of the services, hosts
                        the scoreboard and updates the scores. You are asked to
                        attack the vulnerable machines of the other teams to
                        retrieve proofs of successful exploitation (flags), and
                        to submit them to the flag submission service to score
                        points. At the same time you must defend the services
                        installed on your own machine. Inside your own network
                        segment you can do whatever you want.
                    </Text>
                    <Text mt="md">
                        Internet access is granted to install new software on
                        the machine and on the laptops of the participants.
                        Interaction between the CTF network and remote servers
                        (starting attacks from the cloud, for instance) is
                        discouraged: bruteforce attacks and large computational
                        resources are not needed to do well here.
                    </Text>
                    <Alert
                        mt="md"
                        variant="light"
                        color="orange"
                        title="Back up before you patch"
                    >
                        If you break your vulnerable machine beyond repair, all
                        the organizers can do is reset it to its original state.
                        Back up your exploits, tools and patches: a reset takes
                        a long time and costs a lot of points.
                    </Alert>
                    <Text mt="md">
                        The default SSH user of the machine is{" "}
                        <Code>root</Code> and the password is your team token,
                        sent to the teams before the competition starts.
                    </Text>
                </Section>

                <Section
                    id="scoring"
                    title="Scoring"
                    icon={<ImTarget size={18} />}
                >
                    <Text>
                        The game is divided in rounds (ticks) of{" "}
                        <b>{secondDurationToString(data.roundTime)}</b>. During
                        each round a bot adds new flags to your vulnerable
                        machine, then checks the integrity of your services by
                        interacting with them and retrieving the flags through
                        legitimate accesses.
                    </Text>
                    <Text mt="md">
                        You gain points by attacking the other teams and by
                        keeping your services up. The total score is the sum of
                        the per service scores, and each of those has two
                        components:
                    </Text>
                    <SimpleGrid cols={{ base: 1, sm: 2 }} mt="md" spacing="md">
                        <Paper withBorder radius="md" p="md">
                            <Group gap="xs">
                                <ThemeIcon
                                    size="sm"
                                    radius="xl"
                                    variant="light"
                                    color="cyan"
                                >
                                    <GiCrosshair size={13} />
                                </ThemeIcon>
                                <Text fw={600}>Offense</Text>
                            </Group>
                            <Text size="sm" c="dimmed" mt={6}>
                                Points for the flags captured from other teams
                                and submitted within their validity period.
                            </Text>
                        </Paper>
                        <Paper withBorder radius="md" p="md">
                            <Group gap="xs">
                                <ThemeIcon
                                    size="sm"
                                    radius="xl"
                                    variant="light"
                                    color="cyan"
                                >
                                    <IoSpeedometer size={13} />
                                </ThemeIcon>
                                <Text fw={600}>SLA</Text>
                            </Group>
                            <Text size="sm" c="dimmed" mt={6}>
                                The availability and correct behaviour of your
                                services, as up ticks over total ticks.
                            </Text>
                        </Paper>
                    </SimpleGrid>
                    <Text mt="lg">
                        The value of a flag stolen by an attacker from a victim
                        is assigned dynamically:
                    </Text>
                    <Snippet>{`scale = 15 * sqrt(5)
norm = ln(ln(5)) / 12
offense_points[flag] = scale / (1+exp((sqrt(score[attacker][service]) - sqrt(score[victim][service]))*norm))
defense_points[flag] = min(victim_score, offense_points)`}</Snippet>
                    <Text mt="md">
                        The attacker gains <Code>offense_points</Code> and the
                        victim loses <Code>defense_points</Code>:
                    </Text>
                    <Snippet>{`# Service base points
score[team][service] = ${data.init_service_points}

# Sum offensive points
for flag in stolen_flags[team][service]:
  score[team][service] += offense_points[flag]

# Subtract defensive points
for flag in lost_flags[team][service]:
  score[team][service] -= defense_points[flag]`}</Snippet>
                    <Text mt="md">
                        The final team score is the sum of the per service
                        scores, each multiplied by that service's SLA.
                    </Text>
                    <Snippet>{`total_score[team] = 0

for service in services:
  # Compute SLA of the service
  sla[team][service] = ticks_up[team][service] / ticks[team][service]
  # Limit scores to 0
  score[team][service] = max(0, score[team][service])
  # Add service score
  total_score[team] += score[team][service] * sla[team][service]`}</Snippet>
                    <List mt="lg" spacing="xs">
                        <List.Item>
                            The SLA is not added to the score, it multiplies it.
                        </List.Item>
                        <List.Item>
                            A flag is worth more or less depending on the
                            difference in service score between the two teams.
                        </List.Item>
                        <List.Item>
                            You gain more by stealing from teams with a higher
                            service score, and less from teams below you.
                        </List.Item>
                    </List>
                </Section>

                <Section
                    id="checks"
                    title="Service checks"
                    icon={<RiRadarLine size={18} />}
                >
                    <Text>
                        For every team the scoreboard lists the total score and,
                        per service, its flag points, the captured and lost
                        flags, the SLA and the status of the checks. At most
                        three kinds of check run on your services each round:
                    </Text>
                    <SimpleGrid cols={{ base: 1, md: 3 }} mt="md" spacing="md">
                        <Paper withBorder radius="md" p="md">
                            <Text fw={600}>Check SLA</Text>
                            <Text size="sm" c="dimmed" mt={4}>
                                Verifies that the service is up and behaves as
                                it should.
                            </Text>
                        </Paper>
                        <Paper withBorder radius="md" p="md">
                            <Text fw={600}>Put flag</Text>
                            <Text size="sm" c="dimmed" mt={4}>
                                Stores a new flag in the service.
                            </Text>
                        </Paper>
                        <Paper withBorder radius="md" p="md">
                            <Text fw={600}>Get flag</Text>
                            <Text size="sm" c="dimmed" mt={4}>
                                Retrieves a flag stored earlier. It is skipped,
                                and shown grey, when there is no valid flag left
                                to look for.
                            </Text>
                        </Paper>
                    </SimpleGrid>
                    <Text mt="lg">
                        A round counts towards <Code>ticks_up</Code> only when
                        every check performed in it succeeded.
                    </Text>
                    <Text mt="md">
                        There are countless ways to break a service, so the
                        scoreboard cannot always tell you exactly what went
                        wrong. Restore the service from your backup and check
                        whether it comes back up in a few minutes.
                    </Text>
                </Section>

                <Section id="flags" title="Flags" icon={<FaFlag size={16} />}>
                    <Text>
                        A flag is 31 uppercase alphanumeric characters followed
                        by <Code>=</Code>, matched by{" "}
                        <Code>{data.flag_regex}</Code>.
                    </Text>
                    <Text mt="md">
                        Submit the flags you steal with an HTTP PUT to the Game
                        System at <Code>http://10.10.0.1:8080/flags</Code>, as
                        an array of strings, with your team token in the{" "}
                        <Code>X-Team-Token</Code> header.
                    </Text>
                    <Alert mt="md" variant="light" color="yellow">
                        {data.submitter_rate_limit ? (
                            <>
                                The endpoint accepts one request per{" "}
                                <b>
                                    {secondDurationToString(
                                        data.submitter_rate_limit / 1000,
                                    )}
                                </b>{" "}
                                and up to
                            </>
                        ) : (
                            <>
                                The endpoint is not rate limited: submit as
                                often as you like, up to
                            </>
                        )}{" "}
                        <b>{data.submitter_flags_limit}</b> flags per request.
                        Anything above that limit is ignored and has to be sent
                        again.
                    </Alert>
                    <Snippet>{`import requests

TEAM_TOKEN = '4242424242424242'

flags = ['AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=', 'BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=']

print(requests.put('http://10.10.0.1:8080/flags', headers={
    'X-Team-Token': TEAM_TOKEN
}, json=flags).text)`}</Snippet>
                    <Text mt="md">
                        You get back one object per submitted flag:
                    </Text>
                    <Snippet>{`{
    "msg": f"[{flag}] {message}",
    "flag": flag,
    "status": "ACCEPTED"/"DENIED"/"RESUBMIT"/"ERROR"
}`}</Snippet>
                    <Text mt="md">Where the message is one of:</Text>
                    <Group gap="xs" mt="xs">
                        {[
                            ["Accepted: X flag points", "green"],
                            ["Denied: invalid flag", "red"],
                            ["Denied: flag from nop team", "gray"],
                            ["Denied: flag is your own", "orange"],
                            ["Denied: flag too old", "grape"],
                            ["Denied: flag already claimed", "yellow"],
                        ].map(([label, color]) => (
                            <Badge key={label} variant="light" color={color}>
                                {label}
                            </Badge>
                        ))}
                    </Group>
                    <Text mt="md">
                        A status code other than 200 means the request was
                        malformed, the team token was not valid or the game has
                        ended; the body always says which.
                    </Text>
                    <Text mt="md">
                        Flags expire after {data.flag_expire_ticks} rounds, so
                        you have{" "}
                        <b>
                            {secondDurationToString(
                                data.roundTime * data.flag_expire_ticks,
                            )}
                        </b>{" "}
                        to steal a flag and submit it. Over the same window the
                        checker tries to retrieve one of the last{" "}
                        {data.flag_expire_ticks} flags from your service to
                        decide whether it is still working.
                    </Text>
                </Section>

                <Section
                    id="flagids"
                    title="Flag IDs"
                    icon={<MdOutlineTag size={20} />}
                >
                    <Text>
                        Some services publish "flag IDs": the extra information
                        an exploit needs to find a specific flag, usually the
                        account that stores it. They are only given for flags
                        that are still valid.
                    </Text>
                    <Text mt="md">
                        Fetch them with an HTTP GET on{" "}
                        <Code>
                            http://10.10.0.1:8081/flagIds?team=0&amp;service=ServiceName&amp;round=1
                        </Code>
                        . Every query parameter is optional and filters the
                        result.
                    </Text>
                    <Snippet>{`{
  "foobar": {
    "1": {
      "5" : {
        "flag_id_description": "flag_id_service_foobar_team_1_round_5"
      }
    },
    ...
  },
  ...
}`}</Snippet>
                    <Text mt="md">
                        The format of a flag ID depends on the service, and a
                        service may well have none.
                    </Text>
                </Section>

                <Section
                    id="fairplay"
                    title="Fair play"
                    icon={<FaHandshake size={18} />}
                >
                    <Text>
                        Everyone should enjoy a fair game, so a few rules:
                    </Text>
                    <List mt="md" spacing="sm">
                        <List.Item>
                            Only targets in <Code>10.60.0.0/16</Code> may be
                            attacked. Players are not targets: no breaking into
                            your opponents' laptops.
                        </List.Item>
                        <List.Item>
                            No attacks against the infrastructure, including
                            denial of service, floods, DNS poisoning, ARP
                            spoofing and man in the middle.
                        </List.Item>
                        <List.Item>
                            No unfair practices: anything meant to hinder others
                            rather than to outplay them. Attacking the
                            availability of another team's service — breaking
                            it, replacing or deleting its flags — belongs here.
                        </List.Item>
                        <List.Item>
                            Sharing flags, exploits or hints between teams is
                            severely prohibited and gets you excluded from the
                            competition.
                        </List.Item>
                        <List.Item>
                            When in doubt, ask the organizers.
                        </List.Item>
                    </List>
                </Section>

                <Space h="xl" />
            </Box>
            <Box w={230} visibleFrom="lg" style={{ flexShrink: 0 }}>
                <TableOfContents />
            </Box>
        </Flex>
    );
};
