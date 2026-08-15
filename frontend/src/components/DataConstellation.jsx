import { useRef, useMemo } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { useTheme } from '../theme/ThemeContext'

// Generates N points roughly on a sphere surface (fibonacci sphere) so the
// "data graph" reads as an orb of connected insights, not a random cloud.
function useFibonacciSphere(count, radius) {
  return useMemo(() => {
    const points = []
    const offset = 2 / count
    const increment = Math.PI * (3 - Math.sqrt(5))
    for (let i = 0; i < count; i++) {
      const y = i * offset - 1 + offset / 2
      const r = Math.sqrt(Math.max(0, 1 - y * y))
      const phi = i * increment
      const x = Math.cos(phi) * r
      const z = Math.sin(phi) * r
      points.push(new THREE.Vector3(x * radius, y * radius, z * radius))
    }
    return points
  }, [count, radius])
}

function Nodes({ isDark }) {
  const groupRef = useRef()
  const points = useFibonacciSphere(42, 2.1)

  // Build edges between nearby nodes so it reads as a "data graph"
  const edges = useMemo(() => {
    const lines = []
    for (let i = 0; i < points.length; i++) {
      let nearest = []
      for (let j = 0; j < points.length; j++) {
        if (i === j) continue
        nearest.push([j, points[i].distanceTo(points[j])])
      }
      nearest.sort((a, b) => a[1] - b[1])
      nearest.slice(0, 2).forEach(([j]) => {
        if (j > i) lines.push([points[i], points[j]])
      })
    }
    return lines
  }, [points])

  useFrame((state, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * 0.12
      groupRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.15) * 0.15
    }
  })

  const nodeColor = isDark ? '#3FE0C5' : '#6C5CE7'
  const edgeColor = isDark ? '#8C7BFF' : '#8C7BFF'

  return (
    <group ref={groupRef}>
      {edges.map(([a, b], idx) => {
        const geometry = new THREE.BufferGeometry().setFromPoints([a, b])
        return (
          <line key={idx} geometry={geometry}>
            <lineBasicMaterial attach="material" color={edgeColor} transparent opacity={isDark ? 0.25 : 0.35} />
          </line>
        )
      })}
      {points.map((p, idx) => (
        <mesh key={idx} position={p}>
          <sphereGeometry args={[idx % 7 === 0 ? 0.06 : 0.035, 12, 12]} />
          <meshStandardMaterial
            color={nodeColor}
            emissive={nodeColor}
            emissiveIntensity={idx % 7 === 0 ? 1.4 : 0.6}
            toneMapped={false}
          />
        </mesh>
      ))}
    </group>
  )
}

function Core({ isDark }) {
  const meshRef = useRef()
  useFrame((state) => {
    if (meshRef.current) {
      const s = 0.9 + Math.sin(state.clock.elapsedTime * 1.2) * 0.05
      meshRef.current.scale.set(s, s, s)
    }
  })
  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[1.1, 1]} />
      <meshStandardMaterial
        color={isDark ? '#111729' : '#ffffff'}
        wireframe
        emissive={isDark ? '#3FE0C5' : '#8C7BFF'}
        emissiveIntensity={0.3}
        transparent
        opacity={0.5}
      />
    </mesh>
  )
}

export default function DataConstellation({ className = '' }) {
  const { isDark } = useTheme()

  return (
    <div className={className} aria-hidden="true">
      <Canvas camera={{ position: [0, 0, 6], fov: 45 }} dpr={[1, 1.5]}>
        <ambientLight intensity={isDark ? 0.4 : 0.7} />
        <pointLight position={[5, 5, 5]} intensity={1.2} color={isDark ? '#3FE0C5' : '#8C7BFF'} />
        <pointLight position={[-5, -3, -5]} intensity={0.8} color="#FF6FB0" />
        <Core isDark={isDark} />
        <Nodes isDark={isDark} />
      </Canvas>
    </div>
  )
}
