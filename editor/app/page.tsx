"use client";

import {
    Alert,
    Anchor,
    AppShell,
    Badge,
    Box,
    Container,
    Grid,
    Group,
    Space,
    Stack,
    Text,
    Title,
} from "@mantine/core";
import { useCallback, useEffect, useState } from "react";
import { Config, defaultConfig, parseConfig } from "@/lib/config";
import { CheckerSection, GameplaySection } from "@/components/GameplaySection";
import { GeneralSection } from "@/components/GeneralSection";
import { NodesSection } from "@/components/NodesSection";
import { OutputPanel } from "@/components/OutputPanel";
import { ResourcesSection } from "@/components/ResourcesSection";
import { TeamsSection } from "@/components/TeamsSection";
import { TimingSection } from "@/components/TimingSection";

const STORAGE_KEY = "ctfbox-editor-config";

export default function EditorPage() {
    // The config is only created in the browser: it contains random tokens, so
    // it must not be part of the prerendered HTML.
    const [config, setConfig] = useState<Config | null>(null);

    useEffect(() => {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            setConfig(saved ? parseConfig(JSON.parse(saved)) : defaultConfig());
        } catch {
            setConfig(defaultConfig());
        }
    }, []);

    useEffect(() => {
        if (!config) return;
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
        } catch {
            // Private browsing and friends: losing the draft is acceptable.
        }
    }, [config]);

    const update = useCallback(
        (patch: Partial<Config>) =>
            setConfig((current) => (current ? { ...current, ...patch } : current)),
        [],
    );

    if (!config) return null;

    return (
        <AppShell header={{ height: 64 }} padding="md">
            <AppShell.Header>
                <Group h="100%" px="lg" wrap="nowrap">
                    <Title order={3}>CTFBox</Title>
                    <Badge variant="light">config editor</Badge>
                    <Box style={{ flex: 1 }} />
                    <Anchor
                        href="https://github.com/domysh/CTFBox"
                        target="_blank"
                        size="sm"
                    >
                        Documentation
                    </Anchor>
                </Group>
            </AppShell.Header>

            <AppShell.Main>
                <Container size="xl">
                    <Space h="md" />
                    <Title order={1}>Competition configuration</Title>
                    <Text c="dimmed" mt={4}>
                        Everything on this page happens in your browser: nothing
                        is uploaded anywhere, and your draft is kept locally
                        until you reset it.
                    </Text>
                    <Space h="lg" />

                    <Grid gutter="lg">
                        <Grid.Col span={{ base: 12, lg: 8 }}>
                            <Stack gap="lg">
                                <GeneralSection
                                    config={config}
                                    update={update}
                                />
                                <TimingSection config={config} update={update} />
                                <GameplaySection
                                    config={config}
                                    update={update}
                                />
                                <CheckerSection config={config} update={update} />
                                <ResourcesSection
                                    config={config}
                                    update={update}
                                />
                                <TeamsSection config={config} update={update} />
                                <NodesSection config={config} update={update} />
                                {!config.server_addr && (
                                    <Alert color="yellow">
                                        Set the server address: without it the
                                        generated WireGuard profiles have no
                                        endpoint to point at.
                                    </Alert>
                                )}
                            </Stack>
                        </Grid.Col>
                        <Grid.Col span={{ base: 12, lg: 4 }}>
                            <Box
                                style={{
                                    position: "sticky",
                                    top: 80,
                                }}
                            >
                                <OutputPanel
                                    config={config}
                                    onImport={setConfig}
                                    onReset={() => setConfig(defaultConfig())}
                                />
                            </Box>
                        </Grid.Col>
                    </Grid>
                    <Space h="xl" />
                </Container>
            </AppShell.Main>
        </AppShell>
    );
}
