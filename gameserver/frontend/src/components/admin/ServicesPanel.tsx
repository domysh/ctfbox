import {
    Badge,
    Button,
    Card,
    NumberInput,
    Switch,
    Table,
    Text,
    TextInput,
    Title,
} from "@mantine/core";
import { useState } from "react";
import {
    AdminService,
    adminSend,
    useAdminMutation,
    useAdminServices,
} from "../../scripts/admin";

const ServiceRow = ({ service }: { service: AdminService }) => {
    const [weight, setWeight] = useState<number | string>(service.weight);
    const [description, setDescription] = useState(service.description);
    const mutate = useAdminMutation((body: object) =>
        adminSend(`/services/${service.name}`, "PATCH", body),
    );
    const dirty =
        Number(weight) !== service.weight || description !== service.description;

    return (
        <Table.Tr>
            <Table.Td>
                {service.name}
                {!service.present && (
                    <Badge ml="xs" size="xs" color="red">
                        checker missing
                    </Badge>
                )}
            </Table.Td>
            <Table.Td>
                <Switch
                    checked={service.enabled}
                    onChange={(event) =>
                        mutate.mutate({ enabled: event.currentTarget.checked })
                    }
                />
            </Table.Td>
            <Table.Td>
                <NumberInput
                    value={weight}
                    onChange={setWeight}
                    min={0.1}
                    step={0.1}
                    w={120}
                />
            </Table.Td>
            <Table.Td>
                <TextInput
                    value={description}
                    placeholder="Shown to the organizers only"
                    onChange={(event) =>
                        setDescription(event.currentTarget.value)
                    }
                />
            </Table.Td>
            <Table.Td>
                <Button
                    size="xs"
                    disabled={!dirty}
                    loading={mutate.isPending}
                    onClick={() =>
                        mutate.mutate({ weight: Number(weight), description })
                    }
                >
                    Save
                </Button>
            </Table.Td>
        </Table.Tr>
    );
};

export const ServicesPanel = () => {
    const services = useAdminServices();
    if (services.isLoading) return <Text>Loading services...</Text>;

    return (
        <Card withBorder padding="md">
            <Title order={4}>Services</Title>
            <Text size="sm" c="dimmed">
                Disabling a service stops its checkers: its score freezes but the
                scoreboard keeps showing it. The weight multiplies the points the
                service contributes to the total.
            </Text>
            <Table striped highlightOnHover mt="sm">
                <Table.Thead>
                    <Table.Tr>
                        <Table.Th>Service</Table.Th>
                        <Table.Th>Checked</Table.Th>
                        <Table.Th>Weight</Table.Th>
                        <Table.Th>Notes</Table.Th>
                        <Table.Th />
                    </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                    {(services.data ?? []).map((service) => (
                        <ServiceRow key={service.name} service={service} />
                    ))}
                </Table.Tbody>
            </Table>
        </Card>
    );
};
