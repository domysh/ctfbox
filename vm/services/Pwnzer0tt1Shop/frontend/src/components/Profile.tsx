import {  useUser } from '../utils/net';
import { MainLayout } from './MainLayout';

export const Profile = () => {

    const user = useUser()

    return <MainLayout>
        <div className="box-wrapper">
            <div className="box">
                <h1 style={{fontSize: "40px"}}>Profile</h1>
                <p><b>Username:</b> {user.data?.username}</p>
                <p><b>Email (private):</b> {user.data?.email}</p>
                <p><b>Login Token:</b> {user.data?.token}</p>
                <p><b>Wallet:</b> {user.data?.wallet}$</p>
                <p><b>Created at:</b> {user.data?.created_at}</p>
            </div>
        </div>
    </MainLayout>
};
