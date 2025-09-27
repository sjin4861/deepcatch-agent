'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { MapRouteMetadata } from '@/types/agent';

declare global {
    interface Window {
        kakao?: any;
    }
}

const KAKAO_APP_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_KEY;
const KAKAO_SCRIPT_ID = 'kakao-maps-sdk';

type MapRoutePreviewProps = {
    metadata: MapRouteMetadata;
};

function formatDuration(minutes: number | undefined | null) {
    if (!minutes || Number.isNaN(minutes)) return null;
    if (minutes < 60) return `${Math.round(minutes)}분`;
    const hours = Math.floor(minutes / 60);
    const remaining = Math.round(minutes % 60);
    if (remaining === 0) {
        return `${hours}시간`;
    }
    return `${hours}시간 ${remaining}분`;
}

export default function MapRoutePreview({ metadata }: MapRoutePreviewProps) {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const [error, setError] = useState<string | null>(null);

    const durationLabel = useMemo(() => formatDuration(metadata.route?.duration_minutes ?? undefined), [metadata.route?.duration_minutes]);
    const distanceLabel = useMemo(() => {
        const distance = metadata.route?.distance_km;
        if (distance == null || Number.isNaN(distance)) {
            return null;
        }
        return `${distance.toFixed(1)}km`;
    }, [metadata.route?.distance_km]);

    useEffect(() => {
        let cleanup: (() => void) | undefined;
        let cancelled = false;

        const initializeMap = () => {
            if (!containerRef.current || !window.kakao?.maps) {
                return;
            }
            const kakao = window.kakao;
            const container = containerRef.current;
            container.innerHTML = '';

            const businesses = metadata.businesses ?? [];
            const arrival = metadata.arrival;

            const businessPositions = businesses.map(biz => ({
                biz,
                point: new kakao.maps.LatLng(biz.lat, biz.lng),
            }));

            const fallbackCenter = arrival
                ? new kakao.maps.LatLng(arrival.lat, arrival.lng)
                : undefined;
            const initialCenter = businessPositions[0]?.point ?? fallbackCenter;

            if (!initialCenter) {
                return;
            }

            const map = new kakao.maps.Map(container, {
                center: initialCenter,
                level: 8,
            });

            const overlays: Array<{ setMap: (mapInstance: any) => void }> = [];
            const bounds = new kakao.maps.LatLngBounds();
            bounds.extend(initialCenter);

            for (const { biz, point } of businessPositions) {
                bounds.extend(point);
                const marker = new kakao.maps.Marker({
                    position: point,
                    map,
                    title: biz.name,
                });
                overlays.push(marker);

                if (biz.name || biz.address) {
                    const infoWindow = new kakao.maps.InfoWindow({
                        content: `\n<div style="padding:6px 8px;font-size:12px;">${biz.name}}</div>`,
                        removable: true,
                    });
                    infoWindow.open(map, marker);
                    overlays.push({
                        setMap: (instance: any) => infoWindow.setMap(instance),
                    });
                }
            }

            try {
                map.setBounds(bounds, 24, 24, 24, 24);
            } catch (err) {
                console.warn('Failed to set Kakao map bounds', err);
            }

            cleanup = () => {
                overlays.forEach(item => {
                    try {
                        item.setMap(null);
                    } catch (err) {
                        // ignore clean-up failures
                    }
                });
                container.innerHTML = '';
            };
        };

        const handleKakaoLoad = () => {
            if (cancelled) return;
            window.kakao.maps.load(() => {
                if (cancelled) return;
                setError(null);
                initializeMap();
            });
        };

        if (typeof window === 'undefined') {
            return () => undefined;
        }

        if (window.kakao && window.kakao.maps) {
            handleKakaoLoad();
        } else {
            if (!KAKAO_APP_KEY) {
                setError('카카오 지도 API 키(NEXT_PUBLIC_KAKAO_MAP_KEY)가 설정되어 있지 않습니다.');
                return () => undefined;
            }
            let script = document.getElementById(KAKAO_SCRIPT_ID) as HTMLScriptElement | null;
            if (script) {
                script.addEventListener('load', handleKakaoLoad);
            } else {
                script = document.createElement('script');
                script.id = KAKAO_SCRIPT_ID;
                script.src = `https://dapi.kakao.com/v2/maps/sdk.js?autoload=false&appkey=${KAKAO_APP_KEY}&libraries=services`;
                script.async = true;
                script.addEventListener('load', handleKakaoLoad);
                script.addEventListener('error', () => {
                    if (!cancelled) {
                        setError('카카오 지도 SDK를 불러오지 못했습니다. 네트워크 상태를 확인하세요.');
                    }
                });
                document.head.appendChild(script);
            }
        }

        return () => {
            cancelled = true;
            const existingScript = document.getElementById(KAKAO_SCRIPT_ID);
            if (existingScript) {
                existingScript.removeEventListener('load', handleKakaoLoad);
            }
            if (cleanup) {
                cleanup();
            }
        };
    }, [metadata]);

    return (
        <div className="space-y-3">
            <div
                ref={containerRef}
                className="h-72 w-full rounded-xl border border-border/40 bg-muted"
            />
            {(distanceLabel || durationLabel) && (
                <p className="text-xs text-muted-foreground">
                    {distanceLabel && <span>거리: {distanceLabel}</span>}
                    {distanceLabel && durationLabel && <span className="mx-1">·</span>}
                    {durationLabel && <span>예상 소요: {durationLabel}</span>}
                </p>
            )}
            {metadata.businesses.length > 0 && (
                <div className="rounded-lg border border-border/40 bg-background/60 p-3">
                    <ul className="mt-2 space-y-1 text-xs text-foreground/80">
                        {metadata.businesses.map(biz => (
                            <li key={`${biz.name}-${biz.lat}-${biz.lng}`}>
                                <span className="font-medium text-foreground">{biz.name}</span>
                                {biz.address && <span className="ml-1 text-muted-foreground">({biz.address})</span>}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
            {error && (
                <p className="text-xs text-destructive">{error}</p>
            )}
        </div>
    );
}
