import { useEffect, useRef } from 'react';
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

export const useStickyScrollableHeader = ({ headHeight, topOffset}: { headHeight: number, topOffset: number }) => {
    const tableRef = useRef<HTMLTableElement>(null);
    const paddingElement = useRef<HTMLDivElement>();
    useEffect(() => {
        // Find the scroll container once and keep reference
        let scrollViewport: HTMLElement | null = null;
        
        // Separate function to calculate and set column widths
        const updateHeaderSizes = () => {
            if (!tableRef.current) return;
            const tHead = tableRef.current.tHead;
            if (!tHead) return;
            
            const tableBody = tableRef.current.tBodies[0];
            const headerRow = tHead.rows[0];
            
            if (tableBody?.rows.length > 0) {
                const firstBodyRow = tableBody.rows[0];
                
                // Set each header column width to match body column width
                for (let i = 0; i < headerRow.cells.length; i++) {
                    if (i < firstBodyRow.cells.length) {
                        const headWidth = headerRow.cells[i].getBoundingClientRect().width;
                        const bodyWidth = firstBodyRow.cells[i].getBoundingClientRect().width;
                        console.log(headWidth, bodyWidth, i)
                        if (bodyWidth > headWidth) {
                            headerRow.cells[i].style.minWidth = `${bodyWidth}px`;
                            headerRow.cells[i].style.width = `${bodyWidth}px`;
                            firstBodyRow.cells[i].style.width = `${bodyWidth}px`;
                            firstBodyRow.cells[i].style.minWidth = `${bodyWidth}px`;
                        }else{
                            headerRow.cells[i].style.minWidth = `${headWidth}px`;
                            headerRow.cells[i].style.width = `${headWidth}px`;
                            firstBodyRow.cells[i].style.width = `${headWidth}px`;
                            firstBodyRow.cells[i].style.minWidth = `${headWidth}px`;
                        }
                    }
                }
            }
        };

        const scrollEvent = () => {
            if (tableRef.current) {
                const tHead = tableRef.current.tHead;
                if (!tHead) return;
                
                // Find the table's scrollable viewport if not already found
                if (!scrollViewport) {
                    scrollViewport = tableRef.current.closest('.mantine-ScrollArea-viewport');
                }
                
                const rect = tableRef.current.getBoundingClientRect();
                const tableBody = tableRef.current.tBodies[0];
                
                if (rect.top < topOffset) {
                    if (!paddingElement.current) {
                        // Add padding to prevent content jump when header becomes fixed
                        // Create a placeholder element for the fixed header
                        // Create placeholder div with random ID for the fixed header
                        const placeholder = document.createElement('div');
                        const randomId = `header-placeholder-${Math.random().toString(36).substring(2, 10)}`;
                        placeholder.id = randomId;
                        placeholder.className = 'header-placeholder';
                        placeholder.style.height = `${topOffset}px`;
                        paddingElement.current = placeholder
                        tableBody.parentNode?.insertBefore(placeholder, tableBody)
                        // Update header sizes when switching to fixed position
                        updateHeaderSizes();
                    }
                    
                    // Apply fixed positioning and set horizontal transform
                    tHead.style.position = "fixed";
                    tHead.style.top = `${topOffset}px`;
                    tHead.style.left = `${rect.left}px`;
                    tHead.style.width = `${rect.width}px`;
                    tHead.style.height = `${headHeight}px`;
                    if (tHead.rows.length > 0) {
                        tHead.rows[0].style.height = `${headHeight}px`;
                    }
                    tHead.style.zIndex = "100";
                    
                } else {
                    // Restore normal positioning
                    tHead.style.position = "static";
                    tHead.style.top = "auto";
                    tHead.style.left = "auto";
                    tHead.style.width = "auto";
                    tHead.style.transform = "none";
                    
                    // Remove padding when header returns to normal flow
                    if (paddingElement.current) {
                        paddingElement.current.remove();
                        paddingElement.current = undefined;
                    }
                }
            }
        };
        
        // Throttle events for better performance
        let ticking = false;
        const throttledEvent = (callback: () => void) => {
            if (!ticking) {
                window.requestAnimationFrame(() => {
                    callback();
                    ticking = false;
                });
                ticking = true;
            }
        };

        const horizontalScrollEvent = () => {
            throttledEvent(scrollEvent)
        }

        // Setup horizontal scroll listener
        const setupHorizontalScrollListener = () => {
            if (tableRef.current) {
                const viewport = (() => {
                    // Try to find any scrollable parent
                    let element: HTMLElement | null = tableRef.current;
                    while (element && element !== document.documentElement) {
                        const style = window.getComputedStyle(element);
                        const hasOverflow = ['auto', 'scroll'].includes(style.overflowX) || 
                                            ['auto', 'scroll'].includes(style.overflowY) ||
                                            ['auto', 'scroll'].includes(style.overflow);
                        const canScroll = element.scrollWidth > element.clientWidth || 
                                         element.scrollHeight > element.clientHeight;
                        
                        if (hasOverflow && canScroll) {
                            return element;
                        }
                        element = element.parentElement;
                    }

                    return document.scrollingElement || document.documentElement;
                })();
                if (viewport) {
                    scrollViewport = viewport as HTMLElement;
                    viewport.addEventListener('scroll', horizontalScrollEvent, { passive: true });
                    return () => viewport.removeEventListener('scroll', horizontalScrollEvent);
                }
            }
            return () => {};
        };
        
        // Regular event handlers
        const handleVerticalScroll = () => throttledEvent(scrollEvent);
        const handleResize = () => throttledEvent(() => {
            updateHeaderSizes();
            scrollEvent();
        });

        // Add event listeners
        document.addEventListener("scroll", handleVerticalScroll);
        window.addEventListener("resize", handleResize);
        
        // Setup horizontal scroll listener with delay to ensure DOM is ready
        let cleanupHorizontal = setupHorizontalScrollListener();
        
        // Handle potential DOM changes
        setTimeout(() => {
            cleanupHorizontal();
            cleanupHorizontal = setupHorizontalScrollListener();
        }, 500);
        
        // Initialize state on mount
        scrollEvent();
        
        return () => {
            document.removeEventListener("scroll", handleVerticalScroll);
            window.removeEventListener("resize", handleResize);
            cleanupHorizontal();
        };
    }, []);
    return tableRef
}