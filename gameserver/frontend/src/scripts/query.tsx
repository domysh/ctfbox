import { useQuery } from "@tanstack/react-query";


const baseUrl = import.meta.env.DEV?"http://127.0.0.1:8888":""

export type TeamStatusInfo = {
    id: number,
    name: string,
    shortname: string,
    host: string,
    image: string,
    nop: boolean,
}

type Status = {
    teams: TeamStatusInfo[],
    services: {name: string}[],
    start: string,
    end?: string,
    roundTime: number,
    flag_expire_ticks: number,
    submitter_flags_limit: number,
    submitter_rate_limit: number
    current_round: number,
    flag_regex: string,
    init_service_points: number,
}

export type TeamServiceScore = {
    service: string,
    stolen_flags: number,
    lost_flags: number,
    sla: number,
    score: number,
    ticks_up: number,
    ticks_down: number,
    put_flag: number,
    put_flag_msg: string,
    get_flag: number,
    get_flag_msg: string,
    offensive_points: number,
    defensive_points: number,
    sla_check: number,
    sla_check_msg: string,
    final_score: number,
    diff_stolen_flags: number,
    diff_lost_flags: number,
    diff_offensive_points: number,
    diff_defensive_points: number,
    diff_sla: number,
    diff_score: number,
    diff_final_score: number,

}

export type TeamScores = {
    team: string,
    score: number,
    services: TeamServiceScore[]
}

type Scoreboard = {
    round: number,
    scores: TeamScores[]
}

type TeamScoreboardDetails = {
    round: number,
    score: TeamScores
}[]

type ChartInfo = {
    rounds: number,
    scores: {
        team: string,
        score: number,
    }[]
}[]



export const useStatusQuery = () => useQuery({
    queryKey: ["status"],
    queryFn: async () => await fetch(baseUrl+"/api/status").then(c => c.json()) as Status,
    refetchInterval: 1000*3,
    refetchIntervalInBackground: true,
    staleTime: 1000*3,
})

export const useScoreboardQuery = () => useQuery({
    queryKey: ["scoreboard"],
    queryFn: async () => await fetch(baseUrl+"/api/scoreboard").then(c => c.json()) as Scoreboard
})

export const useTeamQuery = (teamId: string) => useQuery({
    queryKey: ["scoreboard", "team", teamId],
    queryFn: async () => await fetch(baseUrl+`/api/team/${teamId}`).then(c => c.json()) as TeamScoreboardDetails
})

export const useChartQuery = () => useQuery({
    queryKey: ["scoreboard", "chart"],
    queryFn: async () => await fetch(baseUrl+"/api/chart").then(c => c.json()) as ChartInfo
})

export const useTeamSolver = () => {
    const configData = useStatusQuery()
    return (host:string) => {
        return configData.data?.teams.find(t => t.host == host)
    }
}