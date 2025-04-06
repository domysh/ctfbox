

export type LoginRequest = {
    username: string,
    password: string
}

export type UserResponse = {
    id: number,
    created_at: string,
    wallet: number,
    username: string,
    token: string,
    email?: string
}

export type RegistrationRequest = {
    username: string,
    password: string,
    email: string,
}

export type RegistrationResponse = {

}

export type SellRequest = {
    title: string,
    description: string,
    price: number,
    secret: string
}

export type LoginResponse = {
    message: string,
    user: UserResponse
}

export type Article = {
    id: number,
    title: string,
    description: string,
    price: number,
    img: string,
    purchased: boolean,
    secret?: string
}
