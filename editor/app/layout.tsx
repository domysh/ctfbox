import type { Metadata } from "next";
import {
    ColorSchemeScript,
    MantineProvider,
    mantineHtmlProps,
} from "@mantine/core";

import "@mantine/core/styles.css";
import "./globals.css";

export const metadata: Metadata = {
    title: "CTFBox Configuration Editor",
    description:
        "Build the config.json of a CTFBox Attack/Defense competition, from a single machine to a distributed deployment.",
};

export default function RootLayout({
    children,
}: Readonly<{ children: React.ReactNode }>) {
    return (
        <html lang="en" {...mantineHtmlProps}>
            <head>
                <ColorSchemeScript defaultColorScheme="dark" />
                <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
            </head>
            <body>
                <MantineProvider
                    defaultColorScheme="dark"
                    theme={{
                        primaryColor: "cyan",
                        components: {
                            // Helper text goes under the field instead of over
                            // it. A form is read down its column of inputs, and
                            // with the description on top a field that has one
                            // (or whose text wraps to a second line) pushes its
                            // input out of line with its neighbours in the grid.
                            InputWrapper: {
                                defaultProps: {
                                    inputWrapperOrder: [
                                        "label",
                                        "input",
                                        "description",
                                        "error",
                                    ],
                                },
                            },
                        },
                    }}
                >
                    {children}
                </MantineProvider>
            </body>
        </html>
    );
}
