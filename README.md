# LRS Portfolio Project

## 1. Overview

이 프로젝트는 **xAPI 기반 이벤트를 수집하고 해석하여 분석 가능한 형태로 만드는 LRS 플랫폼**을 목표로 한다.

핵심 구조:

* **Sender**: 이벤트 생성 및 전송
* **Receiver**: 이벤트 수신, 저장, 해석, 집계

---

## 2. Architecture

```plaintext
Sender → Receiver(LRS) → Profile → Analytics
```

* Sender: 클라이언트 (퀴즈 기반 이벤트 생성)
* Receiver:

  * LRS: raw 데이터 저장
  * Profile: 이벤트 해석 (의미 부여)
  * Analytics: 집계 및 지표 생성

---

## 3. Project Structure

```plaintext
portfolio/
 ├── sender/        # 이벤트 생성 및 전송
 ├── receiver/      # 수신 및 처리 (LRS + Profile + Analytics)
 ├── docker-compose.yml
 ├── .env
 └── README.md
```

---

## 4. Data Flow

```plaintext
1. Sender에서 이벤트 생성
2. Receiver API로 전송 (/statements)
3. LRS에서 raw 데이터 저장
4. Profile에서 이벤트 해석
5. Analytics에서 집계 및 결과 생성
```

---

## 5. Design Principles

* **Raw Data Preservation**

  * 모든 이벤트는 변형 없이 저장한다.

* **Separation of Concerns**

  * LRS: 저장만 담당
  * Profile: 해석 담당
  * Analytics: 결과 생성 담당

* **Extensibility**

  * Profile 변경 시에도 raw 데이터는 유지되어 재처리 가능

---

## 6. Scope (MVP)

* 퀴즈 기반 이벤트 전송
* xAPI 형태의 최소 이벤트 저장
* 기본 집계 (count / timeline)

---

## 7. Future Plan

* Profile 규격 확장
* 다양한 이벤트 타입 지원
* 지표 모델 고도화 (집중도, 성취도 등)
* 배치 처리 도입 (Airflow or Celery)

---

## 8. Notes

* 초기 단계에서는 단순성을 유지한다.
* 과도한 분리(MSA)는 지양한다.
* 데이터 흐름 안정화 이후 구조 확장한다.
