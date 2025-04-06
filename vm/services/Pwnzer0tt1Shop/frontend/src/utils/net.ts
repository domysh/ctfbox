import axios from "axios";
import { Article, LoginRequest, LoginResponse, RegistrationRequest, SellRequest, UserResponse } from "./types";
import { useQuery } from "@tanstack/react-query";

const getUrl = (path:string) => {
    return import.meta.env.DEV? `http://localhost:1234/api${path}` : `/api${path}`;
}

export const loginRequest = async (data: LoginRequest) => {
    return await axios.post<LoginRequest, LoginResponse>(
        getUrl('/login'), data,
        {
            withCredentials:true
        }
    );
}

export const tokenLoginRequest = async (token: string) => {
    return await axios.post<{ token: string }, LoginResponse>(getUrl("/login/token"), { token }, { withCredentials:true })
}

const getUser = () => async () => {
    return await axios.get(getUrl('/user'), {withCredentials:true}).then(res => res.data as UserResponse);
}

const getArticles = () => async () => {
    return await axios.get(getUrl('/articles'), { withCredentials: true }).then(res => res.data as Article[]);
}

export const buyArticle = async (articleId: number) => {
    return await axios.post(getUrl(`/store/${articleId}/buy`), undefined, { withCredentials:true }).then(res => res.data as Article[]);
}

export const donate = async (price: number) => {
    return await axios.post(getUrl('/donate'), { price }, { withCredentials:true }).then(res => res.data);
}

export const registerRequest = async (data: RegistrationRequest) => {
    return await axios.post(getUrl('/register'), data, { withCredentials: true }).then(res => res.data);
}

export const sellArticle = async (aricleInfo: SellRequest) => {
    return await axios.post(getUrl('/sell'), aricleInfo, { withCredentials: true }).then(res => res.data);
}

export const logoutRequest = async () => {
    return await axios.post(getUrl('/logout'), undefined, { withCredentials: true }).then(res => res.data);
}

export const useArticles = () => {
    return useQuery({
        queryKey: ['articles'],
        queryFn: getArticles(),
        retry: 0,
    })
}

export const useUser = () => {
    return useQuery({
        queryKey: ['user'],
        queryFn: getUser(),
        retry: 0
    })
}