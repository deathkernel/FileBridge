import { Canvas } from "@react-three/fiber";
import { Float, MeshDistortMaterial, Sphere, Stars } from "@react-three/drei";
import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import type { Group } from "three";

function OrbitalCore() {
  const group = useRef<Group>(null);
  useEffect(() => {
    if (!group.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const tween = gsap.to(group.current.rotation, { y: Math.PI * 2, duration: 24, repeat: -1, ease: "none" });
    return () => { tween.kill(); };
  }, []);
  return <group ref={group}>
    <Float speed={1.2} rotationIntensity={0.18} floatIntensity={0.5}>
      <Sphere args={[0.72, 64, 64]}>
        <MeshDistortMaterial color="#ff963f" emissive="#9c3f12" emissiveIntensity={0.42} roughness={0.24} metalness={0.52} distort={0.24} speed={1.6}/>
      </Sphere>
    </Float>
    <mesh rotation={[1.12,0.2,0.38]}><torusGeometry args={[1.02,0.012,12,120]}/><meshBasicMaterial color="#ffc184" transparent opacity={0.72}/></mesh>
    <mesh rotation={[0.45,0.8,1.1]}><torusGeometry args={[1.2,0.008,10,120]}/><meshBasicMaterial color="#e87932" transparent opacity={0.58}/></mesh>
  </group>;
}
export default function StorageScene() {
  if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return null;
  return <Canvas camera={{ position: [0,0,4.2], fov: 42 }} dpr={[1,1.5]} gl={{ alpha:true, antialias:true }}>
    <ambientLight intensity={1.1}/><pointLight position={[2,2,3]} intensity={2.1} color="#ffc184"/>
    <Stars radius={5} depth={2} count={90} factor={2} saturation={0} fade speed={0.35}/>
    <OrbitalCore/>
  </Canvas>;
}