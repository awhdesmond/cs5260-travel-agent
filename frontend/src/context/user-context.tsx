import * as React from 'react'
import { isUndefined } from 'lodash';
import {
  persistUser,
  readUser,
} from '../libs/users';
import type { User } from '../libs/users';

// Actions

export const ActionNameSetUser = "SetUser";

type ActionTypeSetUser = "SetUser";
type ActionType = ActionTypeSetUser;

type ActionValueSetUser = {
  user?: User;
}

type ActionValue = ActionValueSetUser;
type Action = {
  type: ActionType;
  value: ActionValue;
}

type Dispatch = (action: Action) => void

// State and Reducer

interface State {
  user?: User;
}

const reducer = (state: State, action: Action) => {
  switch (action.type) {
    case ActionNameSetUser: {
      const value = action.value as ActionValueSetUser;
      if (!isUndefined(value.user)) {
        persistUser(value.user);
      }
      return { ...state, user: value.user };
    }
    default: {
      throw new Error(`Unhandled action type: ${action.type}`);
    }
  }
}

// Context

interface _UserContext extends State {
  dispatch: Dispatch
}

const UserContext = React.createContext<_UserContext | undefined>(undefined);

type Props = {
  children: React.ReactNode;
}

export const UserProvider = ({ children }: Props) => {
  let user: User | undefined = readUser();
  const [state, dispatch] = React.useReducer(reducer, { user });

  return (
    <UserContext.Provider value={{ ...state, dispatch }}>
      {children}
    </UserContext.Provider>
  );
}

export const useUser = () => {
  const context = React.useContext(UserContext)
  if (isUndefined(context)) {
    throw new Error('useUser must be used within a UserProvider')
  }
  return context;
}
