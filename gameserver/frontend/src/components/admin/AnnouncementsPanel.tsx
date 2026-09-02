import {
    ActionIcon,
    Badge,
    Button,
    Card,
    Group,
    Select,
    Stack,
    Text,
    Textarea,
    TextInput,
    Title,
} from "@mantine/core";
import { useState } from "react";
import { MdDelete } from "react-icons/md";
import {
    adminSend,
    useAdminAnnouncements,
    useAdminMutation,
} from "../../scripts/admin";

const SEVERITY_COLORS: Record<string, string> = {
    info: "blue",
    warning: "yellow",
    critical: "red",
};

export const AnnouncementsPanel = () => {
    const announcements = useAdminAnnouncements();
    const [title, setTitle] = useState("");
    const [body, setBody] = useState("");
    const [severity, setSeverity] = useState<string | null>("info");

    const create = useAdminMutation(
        (payload: object) => adminSend("/announcements", "POST", payload),
        ["announcements"],
    );
    const remove = useAdminMutation(
        (id: number) => adminSend(`/announcements/${id}`, "DELETE"),
        ["announcements"],
    );

    return (
        <Stack gap="lg">
            <Card withBorder padding="md">
                <Title order={4}>Broadcast a message</Title>
                <Text size="sm" c="dimmed">
                    Shown to every player on the scoreboard.
                </Text>
                <Stack mt="md">
                    <Group grow>
                        <TextInput
                            label="Title"
                            value={title}
                            onChange={(event) =>
                                setTitle(event.currentTarget.value)
                            }
                        />
                        <Select
                            label="Severity"
                            data={["info", "warning", "critical"]}
                            value={severity}
                            onChange={setSeverity}
                        />
                    </Group>
                    <Textarea
                        label="Message"
                        minRows={3}
                        autosize
                        value={body}
                        onChange={(event) => setBody(event.currentTarget.value)}
                    />
                    <Group>
                        <Button
                            disabled={!title.trim()}
                            loading={create.isPending}
                            onClick={() =>
                                create.mutate(
                                    { title, body, severity },
                                    {
                                        onSuccess: () => {
                                            setTitle("");
                                            setBody("");
                                        },
                                    },
                                )
                            }
                        >
                            Publish
                        </Button>
                    </Group>
                </Stack>
            </Card>

            <Card withBorder padding="md">
                <Title order={4}>Published</Title>
                <Stack mt="sm">
                    {(announcements.data ?? []).map((item) => (
                        <Group key={item.id} align="start" wrap="nowrap">
                            <Badge
                                color={SEVERITY_COLORS[item.severity] ?? "blue"}
                            >
                                {item.severity}
                            </Badge>
                            <Stack gap={2} style={{ flex: 1 }}>
                                <Text fw={600}>{item.title}</Text>
                                <Text size="sm">{item.body}</Text>
                                <Text size="xs" c="dimmed">
                                    {new Date(item.at).toLocaleString()}
                                </Text>
                            </Stack>
                            <ActionIcon
                                color="red"
                                variant="subtle"
                                loading={remove.isPending}
                                onClick={() => remove.mutate(item.id)}
                            >
                                <MdDelete />
                            </ActionIcon>
                        </Group>
                    ))}
                    {(announcements.data ?? []).length === 0 && (
                        <Text c="dimmed">Nothing published yet.</Text>
                    )}
                </Stack>
            </Card>
        </Stack>
    );
};
