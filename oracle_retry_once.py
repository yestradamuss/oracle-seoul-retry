#!/usr/bin/env python3
"""Oracle Seoul/Chuncheon Always Free E2.1.Micro 인스턴스 1회 생성 시도.

GitHub Actions의 schedule cron이 이 스크립트를 반복 호출한다 (반복 로직은 cron이 담당,
이 스크립트는 "한 번 해보고 결과를 보고"만 한다). PC용 oci_launch_retry.ps1과 판단 로직은
같다: 중복/한도 확인 -> 가용 도메인마다 생성 시도 -> 오류 분류(재고부족/제한/치명적/알수없음).

필요한 환경변수 (워크플로의 GitHub Secrets에서 주입):
  OCI_USER_OCID, OCI_TENANCY_OCID, OCI_FINGERPRINT, OCI_REGION, OCI_KEY_FILE_PATH
  OCI_COMPARTMENT_ID, OCI_SUBNET_ID, OCI_SSH_PUBLIC_KEY
  OCI_DISPLAY_NAME (선택, 기본 tennis-booking-micro), OCI_IMAGE_ID (선택)
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (선택 - 없으면 알림 안 보냄)

종료 코드: 0 = 이번 실행 정상 종료 (생성 성공/이미 있음/재고부족으로 다음에 재시도 모두 포함)
           1 = 치명적 오류 (설정/인증/한도) - GitHub가 실행 실패로 표시해 이메일로 알려준다
"""
import os
import sys
import time
import urllib.parse
import urllib.request

import oci

SHAPE = "VM.Standard.E2.1.Micro"


def env(name, required=True, default=""):
    v = os.environ.get(name, default).strip()
    if required and not v:
        print(f"[fatal] 환경변수 {name} 이 없습니다.", file=sys.stderr)
        sys.exit(1)
    return v


def telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data),
            timeout=15,
        )
    except Exception as e:  # noqa: BLE001
        print(f"텔레그램 알림 실패 (무시하고 계속): {e}", file=sys.stderr)


def main():
    compartment_id = env("OCI_COMPARTMENT_ID")
    subnet_id = env("OCI_SUBNET_ID")
    ssh_key = env("OCI_SSH_PUBLIC_KEY")
    display_name = env("OCI_DISPLAY_NAME", required=False, default="tennis-booking-micro")
    image_id_override = env("OCI_IMAGE_ID", required=False)

    config = {
        "user": env("OCI_USER_OCID"),
        "tenancy": env("OCI_TENANCY_OCID"),
        "fingerprint": env("OCI_FINGERPRINT"),
        "region": env("OCI_REGION"),
        "key_file": env("OCI_KEY_FILE_PATH"),
    }
    oci.config.validate_config(config)

    identity = oci.identity.IdentityClient(config)
    compute = oci.core.ComputeClient(config)
    network = oci.core.VirtualNetworkClient(config)

    try:
        ads = identity.list_availability_domains(compartment_id).data
    except oci.exceptions.ServiceError as e:
        print(f"[fatal] 가용 도메인 조회 실패: {e.message}", file=sys.stderr)
        sys.exit(1)
    if not ads:
        print("[fatal] 가용 도메인이 없습니다.", file=sys.stderr)
        sys.exit(1)

    # ---------------------------------------------------------------- 중복/한도 확인
    try:
        instances = oci.pagination.list_call_get_all_results(compute.list_instances, compartment_id).data
    except oci.exceptions.ServiceError as e:
        print(f"[fatal] 인스턴스 목록 조회 실패: {e.message}", file=sys.stderr)
        sys.exit(1)
    live = [i for i in instances if i.lifecycle_state not in ("TERMINATED", "TERMINATING")]
    same = [i for i in live if i.display_name == display_name]
    if same:
        print(f"이미 '{display_name}' 인스턴스가 있습니다 ({same[0].lifecycle_state}). 조용히 종료합니다.")
        return 0
    micro = [i for i in live if i.shape == SHAPE]
    if len(micro) >= 2:
        print(f"[fatal] 무료 한도(Micro 2대)에 도달했습니다 ({len(micro)}대). 콘솔을 확인하세요.", file=sys.stderr)
        sys.exit(1)

    # ---------------------------------------------------------------- 이미지
    image_id = image_id_override
    if not image_id:
        try:
            images = compute.list_images(
                compartment_id,
                shape=SHAPE,
                operating_system="Canonical Ubuntu",
                sort_by="TIMECREATED",
                sort_order="DESC",
                limit=5,
            ).data
        except oci.exceptions.ServiceError as e:
            print(f"[fatal] 이미지 조회 실패: {e.message}", file=sys.stderr)
            sys.exit(1)
        if not images:
            print("[fatal] 이미지를 찾지 못했습니다. OCI_IMAGE_ID를 직접 지정하세요.", file=sys.stderr)
            sys.exit(1)
        image_id = images[0].id

    # ---------------------------------------------------------------- 가용 도메인마다 생성 시도
    last_error = None
    for ad in ads:
        try:
            details = oci.core.models.LaunchInstanceDetails(
                availability_domain=ad.name,
                compartment_id=compartment_id,
                shape=SHAPE,
                display_name=display_name,
                create_vnic_details=oci.core.models.CreateVnicDetails(
                    subnet_id=subnet_id, assign_public_ip=True
                ),
                source_details=oci.core.models.InstanceSourceViaImageDetails(
                    image_id=image_id, boot_volume_size_in_gbs=50
                ),
                metadata={"ssh_authorized_keys": ssh_key},
            )
            result = compute.launch_instance(details).data
            print(f"생성 성공: {result.id} ({ad.name})")
        except oci.exceptions.ServiceError as e:
            last_error = e
            msg = e.message or ""
            if "Out of host capacity" in msg or e.code == "OutOfCapacity":
                print(f"[capacity] {ad.name}: 재고 부족")
                continue
            if e.status == 429:
                print(f"[rate] {ad.name}: 요청 제한(429)")
                continue
            if e.code == "LimitExceeded":
                print(f"[fatal] 한도 초과: {msg}", file=sys.stderr)
                sys.exit(1)
            if e.status in (400, 401, 404) or e.code in (
                "NotAuthenticated", "NotAuthorized", "InvalidParameter", "MissingParameter",
            ):
                print(f"[fatal] 설정/인증 오류: {msg}", file=sys.stderr)
                sys.exit(1)
            print(f"[unknown] {ad.name}: {msg}")
            continue
        else:
            # 공용 IP가 붙을 때까지 잠깐 재조회 (최대 ~100초)
            public_ip = ""
            for _ in range(10):
                vnics = compute.list_vnic_attachments(compartment_id, instance_id=result.id).data
                if vnics:
                    vnic = network.get_vnic(vnics[0].vnic_id).data
                    if vnic.public_ip:
                        public_ip = vnic.public_ip
                        break
                time.sleep(10)
            telegram(f"🎉 [오라클] 서울 무료 서버 생성 성공! 공용 IP: {public_ip or '(아직 조회 안 됨 - 콘솔 확인)'}")
            return 0

    print(f"이번 실행에서는 확보하지 못했습니다 (마지막: {last_error}). 다음 cron에서 재시도합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
