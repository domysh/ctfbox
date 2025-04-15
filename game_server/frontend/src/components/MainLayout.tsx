import { AppShell, Box, Button, Container, Image, Loader, LoadingOverlay, Space, Title } from "@mantine/core"
import { Link } from "react-router-dom"
import { RulesContent } from "../pages/RulesContent"
import { ScoreboardPage } from "../pages/ScoreboardPage"
import { ScoreboardTeamDetail } from "../pages/ScoreboardTeamDetail"
import { useStatusQuery } from "../scripts/query"
import { useEffect, useMemo, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { NotFoundContent } from "./NotFoundContent"
import { useGlobalState } from "../scripts/utils"

type Pages = "rules" | "scoreboard" | "scoreboard-team" | "not-found" | "loading"

export const MainLayout = ({ page }: { page:Pages }) => {
    const config = useStatusQuery()
    const [oldRound, setOldRound] = useState(-1)
    const queryClient = useQueryClient()
    const [firstLoading, setFirstLoading] = useState(false)

    const { headerComponents, setHeaderComponents, loading } = useGlobalState()

    useEffect(()=>{
        if (!config.isFetching && oldRound != config.data?.current_round) {
            setOldRound(config.data?.current_round??-1)
            queryClient.invalidateQueries({
                queryKey: ["scoreboard"]
            })
        }
    }, [config.isFetching])

    useEffect(()=>{
      if (!firstLoading){
        setFirstLoading(true)
        return
      }
      setHeaderComponents(null)
    }, [page])

    const renderedPage = useMemo(() => {
        if (page == "not-found") return <NotFoundContent key="not-found" />
        if (page == "rules") return <RulesContent key="rules" />
        if (page == "scoreboard") return <ScoreboardPage key="scoreboard" />
        if (page == "scoreboard-team") return <ScoreboardTeamDetail key="scoreboard-team" />
        return <Loader size={40} />
    }, [page])

    return <AppShell
        header={{ height: 60 }}
        padding="md"
    >
    <AppShell.Header>
      <Box className='center-flex' style={{ height: "100%" }} >
        <Space w="md" />
        <Image src="/logo.png" alt="Oasis Logo" width={40} height={40} />
        <Title ml="5px" order={2}>
          Oasis
        </Title>
        <Box flex={1} />
        {headerComponents}
        <Box className="center-flex">
          <Title order={5}>
            <Link to="/rules">
                <Button color="cyan" variant={page == "rules"?"filled":"outline"}>
                    Rules
                </Button>
            </Link>
          </Title>
          <Space w="md" />
          <Title order={5}>
            <Link to="/scoreboard">
                <Button color="cyan" variant={page == "scoreboard"?"filled":"outline"}>
                    Scoreboard
                </Button>
            </Link>
          </Title>
          <Space w="md" />
        </Box>
      </Box>
    </AppShell.Header>
    <AppShell.Main style={{ position: 'relative' }}>
        <LoadingOverlay 
            visible={loading} 
            zIndex={1000}
            overlayProps={{ blur: 2 }}
            loaderProps={{ size: 'xl', color: 'cyan' }}
        />
        <Container fluid>
            {renderedPage}
        </Container>
    </AppShell.Main>
  </AppShell> 
}