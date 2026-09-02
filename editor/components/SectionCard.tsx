"use client";

import { Card, Group, Space, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

export const SectionCard = ({
    title,
    description,
    icon,
    actions,
    children,
}: {
    title: string;
    description?: string;
    icon?: ReactNode;
    actions?: ReactNode;
    children: ReactNode;
}) => (
    <Card withBorder radius="md" padding="lg">
        <Group align="center" wrap="nowrap" mb={description ? 4 : "md"}>
            {icon}
            <Title order={4}>{title}</Title>
            <div style={{ flex: 1 }} />
            {actions}
        </Group>
        {description && (
            <>
                <Text size="sm" c="dimmed">
                    {description}
                </Text>
                <Space h="md" />
            </>
        )}
        {children}
    </Card>
);
