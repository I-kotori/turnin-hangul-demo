#include <algorithm>
#include <iostream>
#include <vector>
#include "정렬 도우미.h"

// 알고리즘 과제: 한글 주석과 문자열이 PDF에서도 읽혀야 합니다.
// 탭 들여쓰기, 영문 identifiers, 숫자 0123456789를 함께 확인합니다.
// 실제 학생 제출물이 아닌, 로컬 시연을 위해 작성한 예제입니다.

// 두 정렬된 구간을 하나의 정렬된 구간으로 합칩니다.
void merge_ranges(std::vector<int>& values, int begin, int middle, int end) {
    std::vector<int> merged;
    int left = begin;
    int right = middle;

    while (left < middle && right < end) {
        if (values[left] <= values[right]) {
            merged.push_back(values[left++]);
        } else {
            merged.push_back(values[right++]);
        }
    }

    // 남은 원소를 붙여 원래의 원소 개수를 보존합니다.
    while (left < middle) {
        merged.push_back(values[left++]);
    }
    while (right < end) {
        merged.push_back(values[right++]);
    }
    std::copy(merged.begin(), merged.end(), values.begin() + begin);
}

// 종료 조건: 원소가 없거나 하나면 이미 정렬된 상태입니다.
void merge_sort(std::vector<int>& values, int begin, int end) {
    if (end - begin <= 1) {
        return;
    }

    const int middle = begin + (end - begin) / 2;
    merge_sort(values, begin, middle);
    merge_sort(values, middle, end);
    merge_ranges(values, begin, middle, end);
}

// 찾는 값의 인덱스를 반환하며, 없으면 -1을 반환합니다.
int find_value(const std::vector<int>& values, int target) {
    int left = 0;
    int right = static_cast<int>(values.size());

    while (left < right) {
        const int middle = left + (right - left) / 2;
        if (values[middle] < target) {
            left = middle + 1;
        } else {
            right = middle;
        }
    }

    if (left < static_cast<int>(values.size()) && values[left] == target) {
        return left;
    }
    return -1;
}

int main() {
	std::vector<int> values = {9, 2, 7, 1, 5};
	merge_sort(values, 0, static_cast<int>(values.size()));
	std::cout << "정렬 결과: ";
	for (const int value : values) {
		std::cout << value << ' ';
	}
	std::cout << '\n';
	std::cout << "숫자 7의 위치: " << find_value(values, 7) << '\n';
	print_complete();
	return 0;
}

// 긴 주석 줄바꿈 확인: 이 문장은 열의 너비를 넘으면 자연스럽게 다음 줄로 이어져야 하고, 이어지는 부분에는 새 소스 줄 번호가 붙지 않아야 합니다. 한글과 English를 섞어도 글자가 잘리거나 옆 열과 겹치면 안 됩니다.
// 문자열 안전성 확인: <tag> & "quotes" $HOME $(echo demo) ; 모두 소스 문자 그대로 출력됩니다.
