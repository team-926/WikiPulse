package io.wikipulse.backend.matching;

/**
 * 재시도해도 소용없는 하드 전송 실패 (WP-66): 인증/키 만료(401·403), 쿼터·과금(402),
 * GMS 공유 예산 소진 신호(429), 기타 비재시도 4xx. 재시도하지 않고 회로에 기록한다 —
 * 지속 조건이면 회로가 열려 죽은 게이트웨이를 폴마다 두들기지 않는다.
 *
 * <p>🔴 GMS 는 팀 공유 키(크레딧 유한·만료 있음)라, 크레딧 소진·키 만료를 전이성으로 오인해
 * 재시도하면 유한 예산을 더 태운다. 그래서 하드로 분류해 재시도 0 + 회로 개방으로 간다.
 */
public class HardUpstreamException extends UpstreamTransportException {

    public HardUpstreamException(String message, Throwable cause) {
        super(message, cause);
    }
}
