"use client";

import {
    Alert,
    Button,
    Card,
    Code,
    CopyButton,
    Group,
    Modal,
    Stack,
    Tabs,
    Text,
    Textarea,
    Title,
} from "@mantine/core";
import { useMemo, useState } from "react";
import { MdDownload, MdUpload, MdRestartAlt } from "react-icons/md";
import { Config, configToJson } from "@/lib/config";
import {
    ImportError,
    compressConfig,
    downloadConfig,
    importConfig,
} from "@/lib/transfer";

const CopyAction = ({
    value,
    label,
    variant = "filled",
}: {
    value: string;
    label: string;
    variant?: string;
}) => (
    <CopyButton value={value} timeout={2000}>
        {({ copied, copy }) => (
            <Button
                variant={copied ? "filled" : variant}
                color={copied ? "teal" : undefined}
                onClick={copy}
            >
                {copied ? "Copied!" : label}
            </Button>
        )}
    </CopyButton>
);

export const OutputPanel = ({
    config,
    onImport,
    onReset,
}: {
    config: Config;
    onImport: (config: Config) => void;
    onReset: () => void;
}) => {
    const json = useMemo(() => configToJson(config), [config]);
    const compressed = useMemo(() => compressConfig(config), [config]);
    const [importOpen, setImportOpen] = useState(false);
    const [importText, setImportText] = useState("");
    const [importError, setImportError] = useState<string | null>(null);

    const runImport = (text: string) => {
        try {
            onImport(importConfig(text));
            setImportOpen(false);
            setImportText("");
            setImportError(null);
        } catch (error) {
            setImportError(
                error instanceof ImportError
                    ? error.message
                    : (error as Error).message,
            );
        }
    };

    return (
        <Card withBorder radius="md" padding="lg">
            <Title order={4}>Your configuration</Title>
            <Text size="sm" c="dimmed" mt={4}>
                Save it as <Code>config.json</Code> next to{" "}
                <Code>run.py</Code>, or paste the compressed string when{" "}
                <Code>./run.py start</Code> asks for it.
            </Text>

            <Group mt="md" gap="xs" wrap="wrap">
                <CopyAction value={compressed} label="Copy compressed" />
                <CopyAction value={json} label="Copy JSON" variant="light" />
                <Button
                    variant="light"
                    leftSection={<MdDownload />}
                    onClick={() => downloadConfig(config)}
                >
                    Download
                </Button>
                <Button
                    variant="light"
                    leftSection={<MdUpload />}
                    onClick={() => setImportOpen(true)}
                >
                    Import
                </Button>
                <Button
                    variant="subtle"
                    color="red"
                    leftSection={<MdRestartAlt />}
                    onClick={onReset}
                >
                    Reset
                </Button>
            </Group>

            <Tabs defaultValue="json" mt="lg">
                <Tabs.List>
                    <Tabs.Tab value="json">config.json</Tabs.Tab>
                    <Tabs.Tab value="compressed">Compressed</Tabs.Tab>
                </Tabs.List>
                <Tabs.Panel value="json" pt="sm">
                    <pre className="config-preview">{json}</pre>
                </Tabs.Panel>
                <Tabs.Panel value="compressed" pt="sm">
                    <Text size="xs" c="dimmed" mb="xs">
                        {compressed.length} characters, zlib + base64.
                    </Text>
                    <pre
                        className="config-preview"
                        style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}
                    >
                        {compressed}
                    </pre>
                </Tabs.Panel>
            </Tabs>

            <Modal
                opened={importOpen}
                onClose={() => setImportOpen(false)}
                title="Import a configuration"
                size="lg"
            >
                <Stack>
                    <Text size="sm" c="dimmed">
                        Paste a <Code>config.json</Code> or a compressed string,
                        or pick the file.
                    </Text>
                    <input
                        type="file"
                        accept=".json,application/json,text/plain"
                        onChange={(event) => {
                            const file = event.currentTarget.files?.[0];
                            if (!file) return;
                            file.text().then(runImport);
                        }}
                    />
                    <Textarea
                        autosize
                        minRows={6}
                        maxRows={14}
                        placeholder='{ "gameserver_token": ... }'
                        value={importText}
                        onChange={(event) =>
                            setImportText(event.currentTarget.value)
                        }
                    />
                    {importError && <Alert color="red">{importError}</Alert>}
                    <Button
                        disabled={!importText.trim()}
                        onClick={() => runImport(importText)}
                    >
                        Import
                    </Button>
                </Stack>
            </Modal>
        </Card>
    );
};
