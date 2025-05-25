import {
    ActionIcon,
    Box,
    Pill,
    ScrollAreaAutosize,
    Space,
    Table,
    Text,
    Title,
} from "@mantine/core";
import {
    TeamScores,
    useScoreboardQuery,
    useStatusQuery,
    useTeamQuery,
    useTeamSolver,
} from "../scripts/query";
import { LineChart } from "@mantine/charts";
import {
    hashedColor,
    scoreBoardSortFunction,
    useGlobalState,
    useStickyScrollableHeader,
} from "../scripts/utils";
import { MdGroups } from "react-icons/md";
import { FaHashtag } from "react-icons/fa6";
import { ImTarget } from "react-icons/im";
import { FaServer } from "react-icons/fa6";
import { ServiceScoreData } from "../components/ServiceScoreData";
import { RoundCounter } from "../components/RoundCounter";
import { useNavigate, useParams } from "react-router-dom";
import { NotFoundContent } from "../components/NotFoundContent";
import { DiffArrow } from "../components/DiffArrow";
import { useEffect, useMemo, memo, useState, useRef } from "react";
import { IoMdArrowRoundBack } from "react-icons/io";

const TeamRoundRow = memo(
    ({
        round,
        currentTeam,
        services,
    }: {
        round: { round: number; score: TeamScores };
        currentTeam?: { name: string };
        services: { name: string }[];
    }) => {
        return (
            <Table.Tr>
                <Table.Td px="md">
                    <Box className="center-flex">
                        <Text>{round.round}</Text>
                    </Box>
                </Table.Td>
                <Table.Td>
                    <Box className="center-flex-col">
                        <Text>{currentTeam?.name ?? "Unknown Team"}</Text>
                        <Space h="3px" />
                        <Pill
                            style={{
                                backgroundColor:
                                    "var(--mantine-color-cyan-filled)",
                                color: "white",
                                fontWeight: "bold",
                            }}
                        >
                            {round.score.team}
                        </Pill>
                    </Box>
                </Table.Td>
                <Table.Td>
                    <Box className="center-flex-row">
                        <Text
                            className="center-flex"
                            style={{ fontWeight: "bolder" }}
                        >
                            {round.score.score.toFixed(2)}
                        </Text>
                        <DiffArrow
                            diff={round.score.services.reduce(
                                (acc, d) => d.diff_final_score + acc,
                                0,
                            )}
                        />
                    </Box>
                </Table.Td>
                {services.map((service, i) => (
                    <Table.Td key={i}>
                        <ServiceScoreData
                            score={round.score.services.find(
                                (ele) => ele.service === service.name,
                            )}
                        />
                    </Table.Td>
                ))}
            </Table.Tr>
        );
    },
);

const TableHeader = memo(({ services }: { services: { name: string }[] }) => (
    <Table.Thead h={60}>
        <Table.Tr style={{ backgroundColor: "var(--mantine-color-dark-8)" }}>
            <Table.Th style={{ width: "10px" }}>
                <Box className="center-flex">
                    <FaHashtag size={20} />
                </Box>
            </Table.Th>
            <Table.Th style={{ width: "fit" }}>
                <Box className="center-flex">
                    <MdGroups size={26} />
                    <Space w="xs" />
                    Team
                </Box>
            </Table.Th>
            <Table.Th>
                <Box className="center-flex">
                    <ImTarget size={20} />
                    <Space w="xs" />
                    Score
                </Box>
            </Table.Th>
            {services.map((service) => (
                <Table.Th key={service.name}>
                    <Box className="center-flex" style={{ width: "100%" }}>
                        <FaServer size={20} />
                        <Space w="xs" />
                        {service.name}
                    </Box>
                </Table.Th>
            ))}
        </Table.Tr>
    </Table.Thead>
));

const HeaderComponent = memo(
    ({
        position,
        teamName,
        navigateBack,
    }: {
        position?: number;
        teamName?: string;
        navigateBack: () => void;
    }) => (
        <Box className="center-flex">
            <Text
                style={{ fontWeight: "bold" }}
                className="center-flex"
                component="div"
            >
                <FaHashtag size={20} />
                <Space w="xs" />
                {position ?? "?"}
            </Text>
            <Space w="md" />
            <Text
                style={{ fontWeight: "bold" }}
                className="center-flex"
                component="div"
            >
                <MdGroups size={20} />
                <Space w="xs" />
                {teamName}
            </Text>
            <Space w="md" />
            <ActionIcon
                variant="filled"
                color="cyan"
                onClick={navigateBack}
                style={{ cursor: "pointer" }}
                size="lg"
            >
                <IoMdArrowRoundBack size={24} />
            </ActionIcon>
            <Space w="md" />
        </Box>
    ),
);

export const ScoreboardTeamDetail = () => {
    const { teamId } = useParams();
    const teamIp = useMemo(() => `10.60.${teamId}.1`, [teamId]);

    const teamData = useTeamQuery(teamId ?? "");
    const configData = useStatusQuery();
    const teamSolver = useTeamSolver();
    const scoreboardData = useScoreboardQuery();
    const navigate = useNavigate();
    const setHeaderComponents = useGlobalState(
        (ele) => ele.setHeaderComponents,
    );

    // State per lo scrolling incrementale
    const [visibleItems, setVisibleItems] = useState<number>(20);
    const loaderRef = useRef<HTMLDivElement>(null);

    // Memoize services with proper dependency
    const services = useMemo(
        () => configData.data?.services.sort() ?? [],
        [configData.data?.services],
    );

    // Memoize position with proper dependency
    const position = useMemo(() => {
        const score = scoreboardData.data?.scores.sort(scoreBoardSortFunction);
        if (!score) return undefined;
        const pos = score.findIndex((item) => item.team === teamIp);
        return pos !== -1 ? pos + 1 : undefined;
    }, [scoreboardData.isFetching, teamIp]);

    const currentTeam = useMemo(() => teamSolver(teamIp), [teamSolver, teamIp]);

    const setLoading = useGlobalState((state) => state.setLoading);
    const tableRef = useStickyScrollableHeader({
        headHeight: 60,
        topOffset: 60,
    });

    // Better error handling for sorting
    const sortedTeamData = useMemo(
        () =>
            teamData.data
                ? [...teamData.data].sort((a, b) => b.round - a.round)
                : [],
        [teamData.data],
    );

    // Memoize rows with proper dependencies e applica paginazione
    const rows = useMemo(
        () =>
            sortedTeamData
                .slice(0, visibleItems)
                .map((round) => (
                    <TeamRoundRow
                        key={round.round}
                        round={round}
                        currentTeam={currentTeam}
                        services={services}
                    />
                )),
        [sortedTeamData, currentTeam, services, visibleItems],
    );

    // Calculate chart data points with proper dependencies
    const { minPoints, maxPoints, chartTeamData } = useMemo(() => {
        if (!teamData.data || teamData.data.length === 0) {
            return { minPoints: 0, maxPoints: 0, chartTeamData: [] };
        }

        let min = Infinity;
        let max = 0;

        for (const round of teamData.data) {
            for (const service of round.score.services) {
                if (service.final_score < min) min = service.final_score;
                if (service.final_score > max) max = service.final_score;
            }
        }

        const chartData = [...teamData.data]
            .sort((a, b) => a.round - b.round)
            .map((round) => ({
                round: round.round,
                ...round.score.services.reduce(
                    (acc, score) => ({
                        ...acc,
                        [score.service]: score.final_score.toFixed(2),
                    }),
                    {},
                ),
            }));

        return {
            minPoints:
                min === Infinity
                    ? 0
                    : Math.max(Math.round(min - min * 0.05), 0),
            maxPoints: Math.round(max + max * 0.05),
            chartTeamData: chartData,
        };
    }, [teamData.data]);

    const navigateBack = () => {
        setLoading(true);
        navigate("/scoreboard/");
    };

    // Set header component with proper dependencies
    useEffect(() => {
        setHeaderComponents(
            <HeaderComponent
                position={position}
                teamName={currentTeam?.name ?? "..."}
                navigateBack={navigateBack}
            />,
        );
    }, [position, currentTeam, setHeaderComponents]);

    const dataLoaded = teamData.isSuccess && configData.isSuccess;

    useEffect(() => {
        if (!dataLoaded) {
            setLoading(true);
        } else {
            setLoading(false);
        }
    }, [dataLoaded, setLoading]);

    useEffect(() => {
        const currentLoaderRef = loaderRef.current;

        if (!currentLoaderRef || visibleItems >= sortedTeamData.length) return;

        const observer = new IntersectionObserver(
            (entries) => {
                const first = entries[0];
                if (first.isIntersecting) {
                    setVisibleItems((prev) =>
                        Math.min(prev + 20, sortedTeamData.length),
                    );
                }
            },
            { threshold: 0 },
        );

        observer.observe(currentLoaderRef);

        return () => {
            observer.disconnect();
        };
    }, [loaderRef, visibleItems, sortedTeamData.length]);

    if (teamData.isError || configData.isError) {
        return <Box>Error loading team data. Please try again.</Box>;
    }

    if (!dataLoaded) return <></>;

    if (currentTeam == null && configData.isSuccess) {
        return <NotFoundContent />;
    }

    return (
        <Box>
            <Title order={1} mb="60px" mt="xs">
                {currentTeam?.name} Scoreboard
            </Title>
            <LineChart
                yAxisProps={{
                    domain: [minPoints, maxPoints],
                }}
                connectNulls
                data={chartTeamData}
                dataKey="round"
                yAxisLabel="Points"
                xAxisLabel="Round"
                series={services.map((service) => ({
                    name: service.name,
                    color: hashedColor(service.name),
                }))}
                withLegend
                legendProps={{ verticalAlign: "bottom" }}
                curveType="linear"
                h={450}
            />

            <RoundCounter />
            <Space h="lg" />

            <ScrollAreaAutosize>
                <Table striped highlightOnHover ref={tableRef}>
                    <TableHeader services={services} />
                    <Table.Tbody>{rows}</Table.Tbody>
                </Table>
                {visibleItems < sortedTeamData.length && (
                    <Box py="md" ta="center" ref={loaderRef}>
                        <Text size="sm" c="dimmed">
                            Loading more rounds...
                        </Text>
                    </Box>
                )}
            </ScrollAreaAutosize>
        </Box>
    );
};
