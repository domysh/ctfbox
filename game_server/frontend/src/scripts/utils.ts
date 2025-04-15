import { create } from 'zustand'

export function stringToHash(string:string) {

    let hash = 0;

    if (string.length == 0) return hash;

    for (let i = 0; i < string.length; i++) {
        let char = string.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }

    return hash;
}

export const hashedColor = (string:string) => {
    return GRAPH_COLOR_PALETTE[Math.abs(stringToHash(string)) % GRAPH_COLOR_PALETTE.length]
}

export const GRAPH_COLOR_PALETTE = [
    "red", "pink", "grape", "violet", "indigo", "blue", "cyan", "teal", "green", "lime", "yellow", "orange"
]

export const scoreBoardSortFunction = (a: {score: number, team: string}, b: {score: number, team: string}) => {
    const scoreDiff = b.score-a.score
    if (scoreDiff !== 0) return scoreDiff
    return a.team.localeCompare(b.team)
}

type GlobalState = {
    headerComponents: React.ReactNode[]|null|React.ReactNode,
    setHeaderComponents: (components: React.ReactNode[]|null|React.ReactNode) => void,
    loading: boolean,
    setLoading: (loading: boolean) => void,
}

export const useGlobalState = create<GlobalState>()((set) => ({
    headerComponents: null,
    setHeaderComponents: (components) => set(() => ({ headerComponents: components })),
    loading: false,
    setLoading: (loading) => set(() => ({ loading }))
}))

