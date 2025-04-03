import { Footer } from "./Footer"
import { Nav } from "./Nav"

export const MainLayout = ( { children }: { children:any } ) => {
    return <>
        <Nav />
        {children}
        <Footer />
    </>
}