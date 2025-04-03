import { Link, useNavigate } from 'react-router-dom';
import { logoutRequest, useUser } from '../utils/net';
import { useQueryClient } from '@tanstack/react-query';

export const Nav = () => {
    const navigate = useNavigate()
    const queryClient = useQueryClient()

    const user = useUser()
    const hasLogin = user.data != null && !user.isError

    return (
    <header className="header">
        <div className="header-content">
        <div className="header-logo center-flex" style={{ gap: 15 }}>
            <img src="/imgs/pwnzer0tt1.png" alt="logo" width={30} height={30} />
            <Link to="/" className="logo">Pwnzer0tt1 Shop</Link>
        </div>
        <nav className="header-navigation">
            { !hasLogin && <Link to="/login">Login</Link> }
            { !hasLogin && <Link to="/register">Register</Link> }
            { hasLogin && <Link to="/store">Store</Link> }
            { hasLogin && <Link to="/donate">Donate</Link> }   
            
            {user ? (
            <>
                { hasLogin && <Link to="/sell">Sell</Link>}
                { hasLogin && <Link to="/profile">Profile</Link> }
                { hasLogin && <Link to="/"
                    style={{ paddingRight: 13 }}
                    onClick={()=>{
                        logoutRequest().then(()=>{
                            queryClient.resetQueries({ queryKey:["user"] })
                            navigate("/")
                        })
                    }}
                >Logout</Link> }
                { hasLogin && <span className="link-button">{user.data?.username}: ${user.data?.wallet?.toFixed(2)}</span> }
            </>
            ) : (
            <Link to="/login" className="link-button">Login</Link>
            )}
        </nav>
        </div>
    </header>
    );
};
