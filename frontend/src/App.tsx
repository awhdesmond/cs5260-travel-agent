import React, { Suspense } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';

import HomePage from './pages/home/HomePage';
import Layout from './layouts/Layout';
import { UserProvider } from './context/user-context';

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { path: "", element: <HomePage /> }
    ],
  },
]);

export default function App() {
  return (
    <Suspense fallback={<div className="p-8">Loading...</div>}>
      <UserProvider>
        <RouterProvider router={router} />
      </UserProvider>
    </Suspense>
  );
}
