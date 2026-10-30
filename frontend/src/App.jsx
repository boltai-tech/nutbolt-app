import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Home from "./pages/Landing";
import Studio from "./pages/Studio";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/studio" element={<Studio />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
