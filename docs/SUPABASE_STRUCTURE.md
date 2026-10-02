# Supabase `personal-projects` 구조 규칙

`personal-projects`(조직 LeeHeeSung Dev, 서울 리전)는 **여러 프로그램이 함께 쓰는 프로젝트**입니다.
각 프로그램은 아래 규칙으로 데이터베이스와 스토리지를 **앱 단위로 분리**해서 사용합니다.
새 프로그램을 붙일 때도 이 문서를 그대로 따릅니다.

## 1. 원칙

1. **앱 하나 = DB 스키마 하나 + DB 전용 계정 하나 + 스토리지 버킷 하나 + 스토리지 서비스 계정 하나.**
2. `public` 스키마는 비워 둡니다. 어떤 앱도 `public`에 테이블을 만들지 않습니다.
3. 앱은 **프로젝트 전체 권한 키(secret / service_role)를 쓰지 않습니다.** 자기 전용 계정으로만 접속해서,
   한 앱의 버그나 키 유출이 다른 앱 데이터에 번지지 않게 합니다.
4. **파일은 스토리지, 정보는 DB.** 파일 내용을 DB에 넣지 않고, DB에는 파일명·크기·버킷 경로 같은 메타데이터만 둡니다.
5. 모든 앱은 `platform.apps`에 한 행으로 등록합니다.

## 2. 이름 규칙

| 대상 | 규칙 | 예 (기업분석 자동화 시스템) |
|---|---|---|
| 앱 키 / DB 스키마 | `snake_case` 영문 | `corp_analysis` |
| DB 전용 계정 | `{스키마}_app` | `corp_analysis_app` |
| 스토리지 버킷 | 스키마의 `_`를 `-`로 (`kebab-case`), 비공개 | `corp-analysis` |
| 버킷 안 경로 | `{용도}/{식별자}.{확장자}` — 영문·숫자·`-`·`_`만 | `source-pdfs/412-93-13689.pdf` |
| 스토리지 서비스 계정 | `svc-{버킷}@personal-projects.local` | `svc-corp-analysis@personal-projects.local` |
| 스토리지 접근 정책 | `{스키마}_svc_{select\|insert\|update\|delete}` | `corp_analysis_svc_select` |

한글 원본 파일명은 경로에 쓰지 않고 앱 스키마의 메타데이터 테이블(`filename` 컬럼)에 저장합니다.

## 3. 현재 구성

```
personal-projects
├─ DB
│  ├─ public                  (비어 있음)
│  ├─ platform
│  │   └─ apps                 앱 레지스트리 (관리자 전용)
│  └─ corp_analysis            기업분석 자동화 시스템  ← 계정 corp_analysis_app 만 접근
│      ├─ companies            기업 분석 결과 (사업자번호당 1행, data json — 표·계정 순서 보존을 위해 jsonb 아님)
│      └─ source_pdfs          원본 PDF 메타데이터 (filename, size_bytes, storage_path)
│      ├─ projects             프로젝트(지원사업 등) — 기업 PDF는 프로젝트 단위로 등록
│      └─ project_companies    프로젝트 참여 기업 (다대다, 기업 삭제 시 cascade)
└─ Storage
   └─ corp-analysis  (비공개 · PDF만 · 파일당 20MB)  ← svc-corp-analysis 계정만 접근
       └─ source-pdfs/{사업자번호}.pdf
```

## 4. 앱이 쓰는 접속 정보 (환경변수)

| 변수 | 용도 |
|---|---|
| `DATABASE_URL` | 앱 전용 DB 계정 연결 문자열 (Session pooler, `{계정}.{프로젝트ref}` 사용자명) |
| `SUPABASE_URL` | `https://zbrmhutsgrhacepmjfau.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | 공개 키 (`sb_publishable_…`) — 서비스 계정 로그인에만 사용 |
| `STORAGE_BUCKET` | 앱 버킷 이름 |
| `STORAGE_SERVICE_EMAIL` / `STORAGE_SERVICE_PASSWORD` | 앱 스토리지 서비스 계정 |

값은 코드·GitHub에 넣지 않고 로컬 `.env`(git 제외)와 배포 환경변수(Render)에만 둡니다.

## 5. 새 앱 추가 절차

`<app>` = 새 앱 키(예: `wbs_analyzer`), `<bucket>` = `<app>`의 `_`→`-`(예: `wbs-analyzer`).

**① DB** (SQL Editor, `postgres` 권한)
```sql
create role <app>_app login noinherit password '<강한 비밀번호>';
create schema <app> authorization postgres;
comment on schema <app> is '<앱 설명>';
revoke all on schema <app> from public;
grant usage on schema <app> to <app>_app;
alter role <app>_app set search_path = <app>;
alter default privileges for role postgres in schema <app>
  grant select, insert, update, delete on tables to <app>_app;
-- 이후 테이블은 반드시 <app>.테이블명 으로 생성
```

**② 스토리지 버킷**
```sql
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('<bucket>', '<bucket>', false, 20971520, array['<허용 MIME>']);
```

**③ 서비스 계정**: Authentication → Users → Add user
(`svc-<bucket>@personal-projects.local`, Auto Confirm 체크, 강한 비밀번호) → 생성된 user id 확인

**④ 버킷 접근 정책** (`<uid>` = ③의 user id)
```sql
create policy "<app>_svc_select" on storage.objects for select to authenticated
  using (bucket_id = '<bucket>' and auth.uid() = '<uid>'::uuid);
create policy "<app>_svc_insert" on storage.objects for insert to authenticated
  with check (bucket_id = '<bucket>' and auth.uid() = '<uid>'::uuid);
create policy "<app>_svc_update" on storage.objects for update to authenticated
  using (bucket_id = '<bucket>' and auth.uid() = '<uid>'::uuid)
  with check (bucket_id = '<bucket>' and auth.uid() = '<uid>'::uuid);
create policy "<app>_svc_delete" on storage.objects for delete to authenticated
  using (bucket_id = '<bucket>' and auth.uid() = '<uid>'::uuid);
```

**⑤ 레지스트리 등록**
```sql
insert into platform.apps (app_key, display_name, db_schema, db_role, storage_bucket, storage_service_user, repository, description)
values ('<app>', '<표시 이름>', '<app>', '<app>_app', '<bucket>', '<uid>', '<저장소 URL>', '<설명>');
```

**⑥ 확인**: 앱 계정으로 다른 앱 스키마의 테이블이 보이지 않는지, 서비스 계정으로 다른 버킷에 업로드가 거부되는지 확인합니다.

## 6. 참고

- 스토리지 접근은 서비스 계정 로그인 토큰(1시간 유효, 앱이 자동 갱신)으로 합니다 — 구현: `backend/object_storage.py`.
- 프로젝트 Authentication에서 이메일 가입이 열려 있어도, 정책이 서비스 계정 user id로 묶여 있어 다른 사용자는 버킷에 접근할 수 없습니다.
