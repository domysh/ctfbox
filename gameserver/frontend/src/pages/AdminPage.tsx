import {
    Alert,
    Badge,
    Box,
    Card,
    Center,
    Code,
    Group,
    Loader,
    Tabs,
    Text,
    Title,
} from "@mantine/core";
import { MdDashboard, MdGroups, MdCampaign, MdVpnKey } from "react-icons/md";
import { FaServer, FaNetworkWired } from "react-icons/fa6";
import { GoGear } from "react-icons/go";
import { RiRadarLine } from "react-icons/ri";
import { ImTarget } from "react-icons/im";
import { BsClipboardData } from "react-icons/bs";
import { useAdminAccess, useAdminOverview } from "../scripts/admin";
import { OverviewPanel } from "../components/admin/OverviewPanel";
import { TeamsPanel } from "../components/admin/TeamsPanel";
import { ServicesPanel } from "../components/admin/ServicesPanel";
import { CheckersPanel } from "../components/admin/CheckersPanel";
import { MonitoringPanel } from "../components/admin/MonitoringPanel";
import { SubmissionsPanel } from "../components/admin/SubmissionsPanel";
import { SettingsPanel } from "../components/admin/SettingsPanel";
import { AnnouncementsPanel } from "../components/admin/AnnouncementsPanel";
import { AuditPanel } from "../components/admin/AuditPanel";

/**
 * Shown to anybody who reaches /admin without an admin tunnel. It is not an
 * error page: players may land here by typing the URL, and the honest answer is
 * simply that this is the organizers' door.
 */
const NoAdminAccess = ({ ip }: { ip?: string }) => (
    <Center style={{ minHeight: "60vh" }}>
        <Card withBorder padding="xl" maw={560}>
            <Group mb="sm">
                <MdVpnKey size={22} />
                <Title order={3}>Organizers only</Title>
            </Group>
            <Text size="sm" c="dimmed">
                The control room is not password protected: it answers only to
                the admin WireGuard profiles handed out by the organizers
                (<Code>router/configs/admins/</Code>). Connect with one of them
                and this page will open on its own.
            </Text>
            {ip && (
                <Text size="xs" c="dimmed" mt="md">
                    You are currently connecting from <Code>{ip}</Code>.
                </Text>
            )}
        </Card>
    </Center>
);

export const AdminPage = () => {
    const access = useAdminAccess();
    const overview = useAdminOverview();

    if (access.isLoading) {
        return (
            <Center style={{ minHeight: "40vh" }}>
                <Loader size="lg" color="cyan" />
            </Center>
        );
    }
    if (!access.data?.admin) return <NoAdminAccess ip={access.data?.ip} />;

    if (overview.isLoading) {
        return (
            <Center style={{ minHeight: "40vh" }}>
                <Loader size="lg" color="cyan" />
            </Center>
        );
    }
    if (overview.isError || !overview.data) {
        return (
            <Alert color="red" title="Cannot load the admin panel">
                {(overview.error as Error)?.message ?? "Unknown error"}
            </Alert>
        );
    }

    const data = overview.data;

    return (
        <Box>
            <Group mb="md">
                <Title order={2}>Control room</Title>
                <Text c="dimmed" size="sm">
                    node {data.node} · server time{" "}
                    {new Date(data.server_time).toLocaleTimeString()}
                </Text>
                <Box flex={1} />
                <Badge variant="light" leftSection={<MdVpnKey size={12} />}>
                    {access.data.ip}
                </Badge>
            </Group>

            {access.data.demo && (
                <Alert
                    mb="lg"
                    color="grape"
                    variant="light"
                    icon={<MdVpnKey size={18} />}
                    title="Read-only demo"
                >
                    There is no game behind this panel: it is the real control
                    room of CTFBox, rebuilt from source and served against a
                    recorded competition. Everything is browsable, nothing can
                    be changed. Run <Code>./run.py start</Code> to get the
                    real one, reachable only through an admin VPN profile.
                </Alert>
            )}

            <Tabs defaultValue="overview" keepMounted={false}>
                <Tabs.List mb="lg">
                    <Tabs.Tab
                        value="overview"
                        leftSection={<MdDashboard size={16} />}
                    >
                        Overview
                    </Tabs.Tab>
                    <Tabs.Tab value="teams" leftSection={<MdGroups size={18} />}>
                        Teams
                    </Tabs.Tab>
                    <Tabs.Tab
                        value="services"
                        leftSection={<FaServer size={14} />}
                    >
                        Services
                    </Tabs.Tab>
                    <Tabs.Tab
                        value="checkers"
                        leftSection={<RiRadarLine size={16} />}
                    >
                        Checkers
                    </Tabs.Tab>
                    <Tabs.Tab
                        value="monitoring"
                        leftSection={<FaNetworkWired size={14} />}
                    >
                        Monitoring
                    </Tabs.Tab>
                    <Tabs.Tab
                        value="submissions"
                        leftSection={<ImTarget size={14} />}
                    >
                        Submissions
                    </Tabs.Tab>
                    <Tabs.Tab
                        value="announcements"
                        leftSection={<MdCampaign size={18} />}
                    >
                        Announcements
                    </Tabs.Tab>
                    <Tabs.Tab value="settings" leftSection={<GoGear size={16} />}>
                        Settings
                    </Tabs.Tab>
                    <Tabs.Tab
                        value="audit"
                        leftSection={<BsClipboardData size={15} />}
                    >
                        Audit
                    </Tabs.Tab>
                </Tabs.List>

                <Tabs.Panel value="overview">
                    <OverviewPanel overview={data} />
                </Tabs.Panel>
                <Tabs.Panel value="teams">
                    <TeamsPanel />
                </Tabs.Panel>
                <Tabs.Panel value="services">
                    <ServicesPanel />
                </Tabs.Panel>
                <Tabs.Panel value="checkers">
                    <CheckersPanel overview={data} />
                </Tabs.Panel>
                <Tabs.Panel value="monitoring">
                    <MonitoringPanel />
                </Tabs.Panel>
                <Tabs.Panel value="submissions">
                    <SubmissionsPanel />
                </Tabs.Panel>
                <Tabs.Panel value="announcements">
                    <AnnouncementsPanel />
                </Tabs.Panel>
                <Tabs.Panel value="settings">
                    <SettingsPanel settings={data.settings} />
                </Tabs.Panel>
                <Tabs.Panel value="audit">
                    <AuditPanel />
                </Tabs.Panel>
            </Tabs>
        </Box>
    );
};
