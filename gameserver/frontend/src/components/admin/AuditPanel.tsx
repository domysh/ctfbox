import { Card, Code, Table, Text, Title } from "@mantine/core";
import { useAuditLog } from "../../scripts/admin";

export const AuditPanel = () => {
    const audit = useAuditLog();

    return (
        <Card withBorder padding="md">
            <Title order={4}>Audit log</Title>
            <Text size="sm" c="dimmed">
                Every privileged action, so that a contested decision can always
                be traced back.
            </Text>
            <Table.ScrollContainer minWidth={700}>
                <Table striped highlightOnHover mt="sm" verticalSpacing="xs">
                    <Table.Thead>
                        <Table.Tr>
                            <Table.Th>When</Table.Th>
                            <Table.Th>Actor</Table.Th>
                            <Table.Th>Action</Table.Th>
                            <Table.Th>Target</Table.Th>
                            <Table.Th>Details</Table.Th>
                        </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                        {(audit.data ?? []).map((entry) => (
                            <Table.Tr key={entry.id}>
                                <Table.Td>
                                    {new Date(entry.at).toLocaleString()}
                                </Table.Td>
                                <Table.Td>{entry.actor}</Table.Td>
                                <Table.Td>
                                    <Code>{entry.action}</Code>
                                </Table.Td>
                                <Table.Td>{entry.target}</Table.Td>
                                <Table.Td>
                                    <Text size="xs">{entry.details}</Text>
                                </Table.Td>
                            </Table.Tr>
                        ))}
                    </Table.Tbody>
                </Table>
            </Table.ScrollContainer>
        </Card>
    );
};
