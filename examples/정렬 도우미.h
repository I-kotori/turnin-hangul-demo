#pragma once
#include <iostream>

// 파일명이 한글이고 공백이 포함되어 있어도 정상적으로 처리합니다.
inline void print_complete() {
    std::cout << "처리가 완료되었습니다. 한글 가나다라마바 사아자차카타파하" << '\n';
}
