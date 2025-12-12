#!/bin/bash

# gcloud config 초기화 스크립트
# 이전 프로젝트 설정을 제거하고 새로 설정할 수 있도록 도와줍니다

echo "현재 gcloud 설정 확인:"
echo "===================="
gcloud config list
echo ""

read -p "프로젝트 설정만 초기화하시겠습니까? (y/n): " answer

if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
    echo ""
    read -p "새로운 프로젝트 ID를 입력하세요 (또는 Enter로 설정 제거): " project_id
    
    if [ -z "$project_id" ]; then
        echo "프로젝트 설정을 제거합니다..."
        gcloud config unset project
        echo "✅ 프로젝트 설정이 제거되었습니다."
    else
        echo "프로젝트를 $project_id로 설정합니다..."
        gcloud config set project "$project_id"
        echo "✅ 프로젝트가 $project_id로 설정되었습니다."
    fi
else
    echo ""
    read -p "전체 설정을 초기화하시겠습니까? (y/n): " answer2
    
    if [ "$answer2" = "y" ] || [ "$answer2" = "Y" ]; then
        echo ""
        echo "⚠️  경고: 이 작업은 모든 gcloud 설정을 삭제합니다."
        read -p "정말로 진행하시겠습니까? (yes 입력): " confirm
        
        if [ "$confirm" = "yes" ]; then
            echo "현재 설정 목록:"
            gcloud config configurations list
            
            echo ""
            read -p "삭제할 설정 이름을 입력하세요 (또는 Enter로 기본 설정만 초기화): " config_name
            
            if [ -z "$config_name" ]; then
                echo "기본 설정의 프로젝트만 제거합니다..."
                gcloud config unset project
            else
                echo "설정 '$config_name'을 삭제합니다..."
                gcloud config configurations delete "$config_name"
            fi
            echo "✅ 설정이 초기화되었습니다."
        else
            echo "작업이 취소되었습니다."
        fi
    else
        echo "작업이 취소되었습니다."
    fi
fi

echo ""
echo "현재 설정:"
gcloud config list

