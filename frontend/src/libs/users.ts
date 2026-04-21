export interface User {
    user_id: string;
    email?: string;
    token: string;
}

const UserTokenKey = "cs5260:users";

export const persistUser = (user) => {
    localStorage.setItem(UserTokenKey, JSON.stringify(user));
}

export const readUser = () => {
    const json = localStorage.getItem(UserTokenKey);
    if (json) {
        return JSON.parse(json);
    }
}
