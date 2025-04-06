import { Link } from "react-router-dom";
import { useUser } from "../utils/net";
import { MainLayout } from "./MainLayout";
import { RainbowText } from "./RainbowText";

export const Home = () => {
  const user = useUser()

  const hasLogin = user.data != null && !user.isError

  return <MainLayout>
    <div className="box-wrapper">
      <div className="home-container">
        <h1 className="home-title">Welcome to the official <RainbowText text="Pwnzer0tt1" style={{ fontWeight: "bolder" }}/> Store!</h1>
        <p className="home-description">Your one-stop solution for all things you need!</p>
        <div style={{marginTop:"50px"}} />
        
        { hasLogin && <Link className="link-button" to="/store" style={{ paddingLeft: 50, paddingRight: 50}}>Visit the store!</Link>}
        { !hasLogin && <>
          <Link className="link-button" to="/login" style={{ paddingLeft: 50, paddingRight: 50}}>Login with your account!</Link>
          <small style={{fontSize:"15px", marginTop: 10}}><Link to="/register">Don't have an account?</Link></small>
        </>}
      </div>
      </div>
    </MainLayout>
};
