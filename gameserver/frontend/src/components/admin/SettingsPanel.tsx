import {
    Alert,
    Button,
    Card,
    Group,
    NumberInput,
    SimpleGrid,
    Stack,
    Text,
    TextInput,
    Title,
} from "@mantine/core";
import { useState } from "react";
import {
    AdminSettings,
    adminSend,
    fromLocalInput,
    toLocalInput,
    useAdminMutation,
} from "../../scripts/admin";

export const SettingsPanel = ({ settings }: { settings: AdminSettings }) => {
    const [tick, setTick] = useState<number | string>(settings.tick_time);
    const [expire, setExpire] = useState<number | string>(
        settings.flag_expire_ticks,
    );
    const [initial, setInitial] = useState<number | string>(
        settings.initial_service_score,
    );
    const [maxFlags, setMaxFlags] = useState<number | string>(
        settings.max_flags_per_request,
    );
    const [timeout, setTimeoutValue] = useState<number | string>(
        settings.submission_timeout ?? 0,
    );
    const [grace, setGrace] = useState<number | string>(settings.grace_time);
    const [checkerTimeout, setCheckerTimeout] = useState<number | string>(
        settings.checker_timeout,
    );
    const [endTime, setEndTime] = useState(toLocalInput(settings.end_time));

    const save = useAdminMutation((body: object) =>
        adminSend("/settings", "PATCH", body),
    );

    return (
        <Stack gap="lg">
            <Alert color="blue" title="Where these settings live">
                Changes take effect immediately and are written back to
                config.json, so a restart keeps them. The tick length changes the
                round boundaries from the next round on.
            </Alert>

            <Card withBorder padding="md">
                <Title order={4}>Game settings</Title>
                <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} mt="md">
                    <NumberInput
                        label="Tick time (s)"
                        description="Length of one round, applied from the next one"
                        value={tick}
                        onChange={setTick}
                        min={5}
                    />
                    <NumberInput
                        label="Flag expiration (ticks)"
                        description="How many rounds a flag stays worth points"
                        value={expire}
                        onChange={setExpire}
                        min={1}
                    />
                    <NumberInput
                        label="Initial service score"
                        description="Only affects services added from now on"
                        value={initial}
                        onChange={setInitial}
                        min={1}
                    />
                    <NumberInput
                        label="Max flags per request"
                        description="Extra flags in a submission are ignored"
                        value={maxFlags}
                        onChange={setMaxFlags}
                        min={1}
                    />
                    <NumberInput
                        label="Submission rate limit (s)"
                        description="0 disables the limit"
                        value={timeout}
                        onChange={setTimeoutValue}
                        min={0}
                        step={0.01}
                        decimalScale={3}
                    />
                    <NumberInput
                        label="Grace time (s)"
                        description="Network locked before the start"
                        value={grace}
                        onChange={setGrace}
                        min={0}
                    />
                    <NumberInput
                        label="Checker timeout (s)"
                        description="How long a single check may take"
                        value={checkerTimeout}
                        onChange={setCheckerTimeout}
                        min={5}
                    />
                    <TextInput
                        type="datetime-local"
                        label="End time"
                        description="Empty means the game never ends on its own"
                        value={endTime}
                        onChange={(event) =>
                            setEndTime(event.currentTarget.value)
                        }
                    />
                </SimpleGrid>
                <Group mt="md">
                    <Button
                        loading={save.isPending}
                        onClick={() =>
                            save.mutate({
                                tick_time: Number(tick),
                                flag_expire_ticks: Number(expire),
                                initial_service_score: Number(initial),
                                max_flags_per_request: Number(maxFlags),
                                grace_time: Number(grace),
                                checker_timeout: Number(checkerTimeout),
                                ...(Number(timeout) > 0
                                    ? { submission_timeout: Number(timeout) }
                                    : { clear_submission_timeout: true }),
                                ...(endTime
                                    ? { end_time: fromLocalInput(endTime) }
                                    : { clear_end_time: true }),
                            })
                        }
                    >
                        Save settings
                    </Button>
                    {save.isError && (
                        <Text c="red" size="sm">
                            {(save.error as Error).message}
                        </Text>
                    )}
                    {save.isSuccess && (
                        <Text c="green" size="sm">
                            Saved
                        </Text>
                    )}
                </Group>
            </Card>

            <Card withBorder padding="md">
                <Title order={4}>Read only</Title>
                <Text size="sm" c="dimmed">
                    Start time: {settings.start_time ?? "-"} · flag format:{" "}
                    <code>{settings.flag_regex}</code>
                </Text>
                <Text size="sm" c="dimmed">
                    Teams, services, VM sizing and the WireGuard topology are
                    part of the infrastructure: change them in config.json and
                    redeploy with <code>./run.py deploy</code>.
                </Text>
            </Card>
        </Stack>
    );
};
